import re

with open('app/copilot.py', 'r') as f:
    content = f.read()

# Replace **name** with __name__ (double underscores)
content = re.sub(r'\*\*name\*\*', '__name__', content)

with open('app/copilot.py', 'w') as f:
    f.write(content)

print("Fixed! Replaced **name** with __name__")
