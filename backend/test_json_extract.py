import sys
sys.path.insert(0, "c:\\Users\\prash\\OneDrive\\Desktop\\Agentic_Ai_Alll_Projects\\Terraform_generator\\backend")

from app.services.smart_terraform_service import _extract_json

# Test 1: Plain JSON
t1 = '{"files": [{"filename": "main.tf", "content": "test"}]}'
print("Test 1 plain:", _extract_json(t1))

# Test 2: JSON in markdown fences
t2 = 'Some explanation\n\n```json\n{"files": [{"filename": "main.tf", "content": "test"}]}\n```\n'
print("Test 2 fenced:", _extract_json(t2))

# Test 3: JSON with nested braces in strings
t3 = '{"files": [{"filename": "main.tf", "content": "resource aws_instance {\\n  ami = \"ami-123\"\\n}"}]}'
print("Test 3 nested:", _extract_json(t3))

# Test 4: Text before JSON
t4 = 'Here is the terraform code:\n\n{"files": [{"filename": "main.tf", "content": "test"}]}\nHope this helps!'
print("Test 4 prose:", _extract_json(t4))

print("All tests passed!")
