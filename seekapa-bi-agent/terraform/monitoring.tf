terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  backend "azurerm" {
    resource_group_name  = "seekapa-terraform-state"
    storage_account_name = "seekapatfstate"
    container_name      = "tfstate"
    key                 = "monitoring.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

provider "kubernetes" {
  host                   = data.azurerm_kubernetes_cluster.main.kube_config.0.host
  client_certificate     = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.client_certificate)
  client_key            = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = data.azurerm_kubernetes_cluster.main.kube_config.0.host
    client_certificate     = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.client_certificate)
    client_key            = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.client_key)
    cluster_ca_certificate = base64decode(data.azurerm_kubernetes_cluster.main.kube_config.0.cluster_ca_certificate)
  }
}

# Data sources
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

data "azurerm_kubernetes_cluster" "main" {
  name                = var.aks_cluster_name
  resource_group_name = var.resource_group_name
}

# Variables
variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "seekapa-rg"
}

variable "aks_cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
  default     = "seekapa-aks-prod"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

# Monitoring namespace
resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
      "environment"                   = var.environment
    }
  }
}

# Prometheus Stack (includes Prometheus, Alertmanager, Grafana)
resource "helm_release" "prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "54.0.0"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  values = [
    templatefile("${path.module}/values/prometheus-stack-values.yaml", {
      grafana_admin_password = random_password.grafana_admin.result
      slack_webhook_url     = var.slack_webhook_url
      pagerduty_routing_key = var.pagerduty_routing_key
      azure_workspace_id    = azurerm_log_analytics_workspace.main.workspace_id
    })
  ]

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage"
    value = "50Gi"
  }

  set {
    name  = "alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage"
    value = "10Gi"
  }

  depends_on = [kubernetes_namespace.monitoring]
}

# Loki for log aggregation
resource "helm_release" "loki" {
  name       = "loki"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki-stack"
  version    = "2.9.11"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  set {
    name  = "loki.persistence.enabled"
    value = "true"
  }

  set {
    name  = "loki.persistence.size"
    value = "50Gi"
  }

  set {
    name  = "promtail.enabled"
    value = "true"
  }

  depends_on = [kubernetes_namespace.monitoring]
}

# Elasticsearch for ELK stack
resource "helm_release" "elasticsearch" {
  name       = "elasticsearch"
  repository = "https://helm.elastic.co"
  chart      = "elasticsearch"
  version    = "8.11.1"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  values = [
    templatefile("${path.module}/values/elasticsearch-values.yaml", {
      storage_size = "100Gi"
      replicas    = 3
    })
  ]

  depends_on = [kubernetes_namespace.monitoring]
}

# Kibana
resource "helm_release" "kibana" {
  name       = "kibana"
  repository = "https://helm.elastic.co"
  chart      = "kibana"
  version    = "8.11.1"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  set {
    name  = "elasticsearchHosts"
    value = "http://elasticsearch-master:9200"
  }

  depends_on = [helm_release.elasticsearch]
}

# Filebeat for log shipping
resource "helm_release" "filebeat" {
  name       = "filebeat"
  repository = "https://helm.elastic.co"
  chart      = "filebeat"
  version    = "8.11.1"
  namespace  = kubernetes_namespace.monitoring.metadata[0].name

  values = [
    templatefile("${path.module}/values/filebeat-values.yaml", {
      elasticsearch_host = "elasticsearch-master:9200"
    })
  ]

  depends_on = [helm_release.elasticsearch]
}

# Azure Application Insights
resource "azurerm_application_insights" "main" {
  name                = "seekapa-bi-agent-insights"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  application_type    = "web"
  retention_in_days   = 90
  sampling_percentage = 100

  tags = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "seekapa-log-analytics"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  sku                = "PerGB2018"
  retention_in_days   = 30

  tags = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Container Insights for AKS
resource "azurerm_log_analytics_solution" "container_insights" {
  solution_name         = "ContainerInsights"
  location              = data.azurerm_resource_group.main.location
  resource_group_name   = data.azurerm_resource_group.main.name
  workspace_resource_id = azurerm_log_analytics_workspace.main.id
  workspace_name        = azurerm_log_analytics_workspace.main.name

  plan {
    publisher = "Microsoft"
    product   = "OMSGallery/ContainerInsights"
  }
}

# Azure Monitor Action Group for alerts
resource "azurerm_monitor_action_group" "main" {
  name                = "seekapa-alerts"
  resource_group_name = data.azurerm_resource_group.main.name
  short_name          = "seekapa"

  email_receiver {
    name          = "sendtoadmin"
    email_address = var.admin_email
  }

  webhook_receiver {
    name        = "slack"
    service_uri = var.slack_webhook_url
  }

  webhook_receiver {
    name        = "pagerduty"
    service_uri = "https://events.pagerduty.com/integration/${var.pagerduty_integration_key}/enqueue"
  }
}

# Metric alerts
resource "azurerm_monitor_metric_alert" "high_cpu" {
  name                = "high-cpu-usage"
  resource_group_name = data.azurerm_resource_group.main.name
  scopes              = [data.azurerm_kubernetes_cluster.main.id]
  description         = "Alert when CPU usage is too high"

  severity    = 2
  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "node_cpu_usage_percentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }
}

resource "azurerm_monitor_metric_alert" "high_memory" {
  name                = "high-memory-usage"
  resource_group_name = data.azurerm_resource_group.main.name
  scopes              = [data.azurerm_kubernetes_cluster.main.id]
  description         = "Alert when memory usage is too high"

  severity    = 2
  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "node_memory_working_set_percentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 85
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }
}

# Grafana admin password
resource "random_password" "grafana_admin" {
  length  = 24
  special = true
}

# Store Grafana password in Key Vault
resource "azurerm_key_vault_secret" "grafana_admin_password" {
  name         = "grafana-admin-password"
  value        = random_password.grafana_admin.result
  key_vault_id = var.key_vault_id

  tags = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Outputs
output "application_insights_connection_string" {
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
  description = "Application Insights connection string"
}

output "application_insights_instrumentation_key" {
  value       = azurerm_application_insights.main.instrumentation_key
  sensitive   = true
  description = "Application Insights instrumentation key"
}

output "log_analytics_workspace_id" {
  value       = azurerm_log_analytics_workspace.main.workspace_id
  description = "Log Analytics workspace ID"
}

output "grafana_url" {
  value       = "https://grafana.${var.domain_name}"
  description = "Grafana dashboard URL"
}

output "kibana_url" {
  value       = "https://kibana.${var.domain_name}"
  description = "Kibana dashboard URL"
}

output "prometheus_url" {
  value       = "http://prometheus-operated.monitoring.svc.cluster.local:9090"
  description = "Prometheus internal URL"
}

# Additional variables
variable "admin_email" {
  description = "Administrator email for alerts"
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  sensitive   = true
}

variable "pagerduty_routing_key" {
  description = "PagerDuty routing key for alerts"
  type        = string
  sensitive   = true
}

variable "pagerduty_integration_key" {
  description = "PagerDuty integration key"
  type        = string
  sensitive   = true
}

variable "key_vault_id" {
  description = "Azure Key Vault ID"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "seekapa.com"
}