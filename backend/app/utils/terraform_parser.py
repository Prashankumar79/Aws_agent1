import re

def parse_terraform_output(raw_output: str) -> dict[str, str]:
    """Parses LLM output containing multiple Terraform files. Returns dict: { filename: code }"""
    result = {}
    pattern = r'FILE:\s*([^\n]+\.tf[^\n]*)\n```(?:hcl|terraform)?\n(.*?)```'
    matches = re.findall(pattern, raw_output, re.DOTALL | re.IGNORECASE)
    for filename, content in matches:
        filename = filename.strip().split("/")[-1]
        content = content.strip()
        if content:
            result[filename] = content
    if not result:
        segments = re.split(r'FILE:\s*', raw_output, flags=re.IGNORECASE)
        for segment in segments[1:]:
            lines = segment.strip().split("\n")
            if not lines:
                continue
            filename = lines[0].strip().split("/")[-1]
            if not filename.endswith(".tf") and not filename.endswith(".tfvars"):
                continue
            code_lines = lines[1:]
            if code_lines and code_lines[0].startswith("```"):
                code_lines = code_lines[1:]
            if code_lines and code_lines[-1].startswith("```"):
                code_lines = code_lines[:-1]
            content = "\n".join(code_lines).strip()
            if content:
                result[filename] = content
    return result

def terraform_files_to_text(terraform_files: dict[str, str]) -> str:
    parts = []
    for filename, content in terraform_files.items():
        parts.append(f"FILE: {filename}\n```hcl\n{content}\n```")
    return "\n\n".join(parts)
