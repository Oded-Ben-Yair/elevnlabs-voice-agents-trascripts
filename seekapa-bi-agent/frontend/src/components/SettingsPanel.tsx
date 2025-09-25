import { motion } from 'framer-motion'
import { Settings, Bell, Palette, Shield } from 'lucide-react'

const SettingsPanel = () => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-6"
    >
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Settings className="w-6 h-6 text-gray-600" />
          <h2 className="text-xl font-semibold">Settings</h2>
        </div>

        {/* Notification Settings */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-4">
            <Bell className="w-5 h-5 text-blue-600" />
            <h3 className="font-medium">Notifications</h3>
          </div>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" defaultChecked />
              <span className="text-sm">Enable push notifications</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" defaultChecked />
              <span className="text-sm">Email digest</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" />
              <span className="text-sm">SMS alerts for critical insights</span>
            </label>
          </div>
        </div>

        {/* Theme Settings */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-4">
            <Palette className="w-5 h-5 text-purple-600" />
            <h3 className="font-medium">Appearance</h3>
          </div>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input type="radio" name="theme" value="light" defaultChecked />
              <span className="text-sm">Light mode</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="radio" name="theme" value="dark" />
              <span className="text-sm">Dark mode</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="radio" name="theme" value="auto" />
              <span className="text-sm">System preference</span>
            </label>
          </div>
        </div>

        {/* Privacy Settings */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-4">
            <Shield className="w-5 h-5 text-green-600" />
            <h3 className="font-medium">Privacy & Security</h3>
          </div>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" defaultChecked />
              <span className="text-sm">Allow data analytics</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" />
              <span className="text-sm">Share usage data</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="rounded" defaultChecked />
              <span className="text-sm">Two-factor authentication</span>
            </label>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

export default SettingsPanel