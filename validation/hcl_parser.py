import hcl2
from typing import Dict, List, Any
from pathlib import Path

class HCLParser:
    """Parse HCL/Terraform files using python-hcl2"""
    
    def __init__(self):
        pass
    
    def parse_file(self, file_path: str) -> Dict:
        """Parse a single HCL file"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return self.parse_string(content)
        except Exception as e:
            return {
                "error": str(e),
                "parsed": False
            }
    
    def parse_string(self, hcl_string: str) -> Dict:
        """Parse HCL string"""
        try:
            parsed = hcl2.loads(hcl_string)
            return {
                "parsed": True,
                "data": parsed,
                "error": None
            }
        except Exception as e:
            return {
                "parsed": False,
                "error": str(e),
                "data": None
            }
    
    def extract_resources(self, parsed_data: Dict) -> List[Dict]:
        """Extract resource blocks from parsed HCL"""
        resources = []
        
        if "resource" in parsed_data:
            for resource_type, resource_blocks in parsed_data["resource"].items():
                for resource_block in resource_blocks:
                    if isinstance(resource_block, dict):
                        for resource_name, resource_config in resource_block.items():
                            resources.append({
                                "type": resource_type,
                                "name": resource_name,
                                "config": resource_config
                            })
        
        return resources
    
    def extract_modules(self, parsed_data: Dict) -> List[Dict]:
        """Extract module blocks from parsed HCL"""
        modules = []
        
        if "module" in parsed_data:
            for module_name, module_config in parsed_data["module"].items():
                if isinstance(module_config, dict):
                    modules.append({
                        "name": module_name,
                        "source": module_config.get("source"),
                        "config": module_config
                    })
        
        return modules
    
    def extract_variables(self, parsed_data: Dict) -> List[Dict]:
        """Extract variable blocks from parsed HCL"""
        variables = []
        
        if "variable" in parsed_data:
            for var_name, var_config in parsed_data["variable"].items():
                if isinstance(var_config, dict):
                    variables.append({
                        "name": var_name,
                        "type": var_config.get("type"),
                        "default": var_config.get("default"),
                        "description": var_config.get("description")
                    })
        
        return variables
    
    def extract_outputs(self, parsed_data: Dict) -> List[Dict]:
        """Extract output blocks from parsed HCL"""
        outputs = []
        
        if "output" in parsed_data:
            for output_name, output_config in parsed_data["output"].items():
                if isinstance(output_config, dict):
                    outputs.append({
                        "name": output_name,
                        "value": output_config.get("value"),
                        "description": output_config.get("description")
                    })
        
        return outputs
    
    def extract_providers(self, parsed_data: Dict) -> List[Dict]:
        """Extract provider blocks from parsed HCL"""
        providers = []
        
        if "provider" in parsed_data:
            for provider_name, provider_config in parsed_data["provider"].items():
                if isinstance(provider_config, dict):
                    providers.append({
                        "name": provider_name,
                        "config": provider_config
                    })
        
        return providers
    
    def get_resource_count(self, parsed_data: Dict) -> int:
        """Get count of resources in parsed HCL"""
        resources = self.extract_resources(parsed_data)
        return len(resources)
    
    def validate_syntax(self, hcl_string: str) -> Dict:
        """Validate HCL syntax"""
        result = self.parse_string(hcl_string)
        
        return {
            "valid": result["parsed"],
            "error": result.get("error")
        }
    
    def compare_resources(self, hcl1: str, hcl2: str) -> Dict:
        """Compare resources between two HCL files"""
        parsed1 = self.parse_string(hcl1)
        parsed2 = self.parse_string(hcl2)
        
        if not parsed1["parsed"] or not parsed2["parsed"]:
            return {
                "comparable": False,
                "error": "Failed to parse one or both HCL files"
            }
        
        resources1 = self.extract_resources(parsed1["data"])
        resources2 = self.extract_resources(parsed2["data"])
        
        # Get resource types
        types1 = {(r["type"], r["name"]) for r in resources1}
        types2 = {(r["type"], r["name"]) for r in resources2}
        
        added = types2 - types1
        removed = types1 - types2
        common = types1 & types2
        
        return {
            "comparable": True,
            "added": list(added),
            "removed": list(removed),
            "common": list(common),
            "count1": len(resources1),
            "count2": len(resources2)
        }
