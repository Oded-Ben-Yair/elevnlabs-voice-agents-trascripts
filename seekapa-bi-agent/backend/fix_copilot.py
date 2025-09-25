with open('app/copilot.py', 'r') as f:
    lines = f.readlines()

# Fix the problematic line
for i, line in enumerate(lines):
    if '**name**' in line:
        lines[i] = 'if __name__ == "__main__":\n'

with open('app/copilot.py', 'w') as f:
    f.writelines(lines)

print("Fixed the __name__ issue!")
