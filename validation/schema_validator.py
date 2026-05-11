from typing import Dict, List
from validation.hcl_parser import HCLParser

class SchemaValidator:
    """Validate Terraform schema and detect hallucinations"""
    
    def __init__(self):
        self.parser = HCLParser()
        self.known_resource_types = self._load_known_types()
    
    def _load_known_types(self) -> set:
        """Load known Terraform resource types"""
        # This would typically be loaded from a database or API
        # For now, include common AWS, GCP, and Azure resources
        return {
            # AWS
            "aws_instance", "aws_s3_bucket", "aws_rds_instance", "aws_vpc",
            "aws_subnet", "aws_security_group", "aws_iam_role", "aws_lambda_function",
            "aws_eks_cluster", "aws_ecs_service", "aws_elb", "aws_alb",
            # GCP
            "google_compute_instance", "google_storage_bucket", "google_sql_database_instance",
            "google_compute_network", "google_compute_subnetwork", "google_container_cluster",
            # Azure
            "azurerm_linux_virtual_machine", "azurerm_storage_account", "azurerm_mssql_database",
            "azurerm_virtual_network", "azurerm_subnet", "azurerm_kubernetes_cluster"
        }
    
    def validate_schema(self, terraform_code: str, design_doc: Dict) -> Dict:
        """Validate Terraform schema against design document"""
        
        # Parse Terraform code
        parsed = self.parser.parse_string(terraform_code)
        
        if not parsed["parsed"]:
            return {
                "valid": False,
                "error": parsed["error"],
                "hallucinations": [],
                "missing": []
            }
        
        # Extract resources
        resources = self.parser.extract_resources(parsed["data"])
        
        # Check for hallucinations (resources not in design)
        hallucinations = self._detect_hallucinations(resources, design_doc)
        
        # Check for missing resources (resources in design but not in code)
        missing = self._detect_missing_resources(resources, design_doc)
        
        # Check for unknown resource types
        unknown_types = self._detect_unknown_types(resources)
        
        return {
            "valid": len(hallucinations) == 0 and len(unknown_types) == 0,
            "hallucinations": hallucinations,
            "missing": missing,
            "unknown_types": unknown_types,
            "resource_count": len(resources)
        }
    
    def _detect_hallucinations(self, resources: List[Dict], design_doc: Dict) -> List[Dict]:
        """Detect resources that weren't in the design document"""
        hallucinations = []
        
        # Get resource types from design
        design_resources = set()
        for component in design_doc.get("components", []):
            design_resources.add(component.get("component_type", ""))
        
        # Check each resource
        for resource in resources:
            resource_type = resource["type"]
            resource_name = resource["name"]
            
            if resource_type not in design_resources:
                hallucinations.append({
                    "type": resource_type,
                    "name": resource_name,
                    "reason": "Resource type not found in design document"
                })
        
        return hallucinations
    
    def _detect_missing_resources(self, resources: List[Dict], design_doc: Dict) -> List[Dict]:
        """Detect resources from design that are missing in code"""
        missing = []
        
        # Get resource types from design
        design_resources = {}
        for component in design_doc.get("components", []):
            resource_type = component.get("component_type", "")
            resource_name = component.get("name", "").lower().replace("-", "_")
            design_resources[resource_type] = resource_name
        
        # Get resource types from code
        code_resources = {}
        for resource in resources:
            code_resources[resource["type"]] = resource["name"]
        
        # Check for missing
        for resource_type, resource_name in design_resources.items():
            if resource_type not in code_resources:
                missing.append({
                    "type": resource_type,
                    "name": resource_name,
                    "reason": "Resource found in design but not in generated code"
                })
        
        return missing
    
    def _detect_unknown_types(self, resources: List[Dict]) -> List[str]:
        """Detect unknown or invalid resource types"""
        unknown = []
        
        for resource in resources:
            resource_type = resource["type"]
            if resource_type not in self.known_resource_types:
                unknown.append(resource_type)
        
        return unknown
    
    def validate_resource_attributes(
        self,
        resource_type: str,
        resource_config: Dict
    ) -> Dict:
        """Validate resource attributes against known schema"""
        errors = []
        
        # Get required attributes for resource type
        required_attrs = self._get_required_attributes(resource_type)
        
        for attr in required_attrs:
            if attr not in resource_config:
                errors.append(f"Missing required attribute: {attr}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def _get_required_attributes(self, resource_type: str) -> List[str]:
        """Get required attributes for a resource type"""
        # This would typically be loaded from Terraform provider schemas
        required_attrs = {
            "aws_instance": ["ami", "instance_type"],
            "aws_s3_bucket": ["bucket"],
            "aws_rds_instance": ["engine", "instance_class"],
            "google_compute_instance": ["machine_type", "zone"],
            "azurerm_linux_virtual_machine": ["resource_group_name", "location", "size"]
        }
        
        return required_attrs.get(resource_type, [])
    
    def detect_circular_dependencies(self, terraform_code: str) -> Dict:
        """Detect circular dependencies in Terraform code"""
        parsed = self.parser.parse_string(terraform_code)
        
        if not parsed["parsed"]:
            return {
                "valid": False,
                "error": parsed["error"],
                "circular_deps": []
            }
        
        resources = self.parser.extract_resources(parsed["data"])
        
        # Build dependency graph
        dependencies = {}
        for resource in resources:
            resource_id = f"{resource['type']}.{resource['name']}"
            deps = self._extract_dependencies(resource["config"])
            dependencies[resource_id] = deps
        
        # Check for circular dependencies
        circular = self._find_circular_dependencies(dependencies)
        
        return {
            "valid": len(circular) == 0,
            "circular_deps": circular
        }
    
    def _extract_dependencies(self, config: Dict) -> List[str]:
        """Extract dependencies from resource configuration"""
        dependencies = []
        
        # Look for references to other resources
        def extract_refs(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    if isinstance(value, dict) and "reference" in value:
                        dependencies.append(value["reference"])
                    else:
                        extract_refs(value, new_path)
            elif isinstance(obj, list):
                for item in obj:
                    extract_refs(item, path)
        
        extract_refs(config)
        return dependencies
    
    def _find_circular_dependencies(self, dependencies: Dict) -> List[List[str]]:
        """Find circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node, path):
            if node in rec_stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:])
                return
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            
            for dep in dependencies.get(node, []):
                dfs(dep, path + [node])
            
            rec_stack.remove(node)
        
        for node in dependencies:
            if node not in visited:
                dfs(node, [])
        
        return cycles
