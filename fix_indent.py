
file_path = r'c:\Users\chait\performanceframework\core\runner.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed_lines = []
for i, line in enumerate(lines):
    # Fix the specific block around 355-360
    # Convert all tabs to 4 spaces
    line = line.replace('\t', '    ')
    fixed_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)
print("Indentation fixed: converted Tabs to 4 Spaces.")
