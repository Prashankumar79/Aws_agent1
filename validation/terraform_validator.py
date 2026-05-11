import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, List

class TerraformValidator:
    """Run terraform validate on generated code"""
    
    def __init__(self):
        self.terraform_path = self._find_terraform()
    
    def _find_terraform(self) -> str:
        """Find terraform executable"""
        try:
            result = subprocess.run(["which", "terraform"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        # Default to terraform in PATH
        return "terraform"
    
    def validate(self, terraform_code: str, working_dir: str = None) -> Dict:
        """Validate Terraform code using terraform validate"""
        
        # Create temporary directory for validation
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write terraform code to main.tf
            main_tf = Path(temp_dir) / "main.tf"
            main_tf.write_text(terraform_code)
            
            # Initialize terraform
            init_result = self._terraform_init(temp_dir)
            if not init_result["success"]:
                return init_result
            
            # Run terraform validate
            validate_result = self._terraform_validate(temp_dir)
            
            return validate_result
    
    def _terraform_init(self, working_dir: str) -> Dict:
        """Run terraform init"""
        try:
            result = subprocess.run(
                [self.terraform_path, "init"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Terraform init timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _terraform_validate(self, working_dir: str) -> Dict:
        """Run terraform validate"""
        try:
            result = subprocess.run(
                [self.terraform_path, "validate"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "valid": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "valid": False,
                "error": "Terraform validate timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "valid": False,
                "error": str(e)
            }
    
    def validate_files(self, file_paths: List[str]) -> Dict:
        """Validate multiple Terraform files"""
        
        # Create temporary directory with all files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy files to temp directory
            for file_path in file_paths:
                file_path = Path(file_path)
                dest = Path(temp_dir) / file_path.name
                dest.write_text(file_path.read_text())
            
            # Initialize and validate
            init_result = self._terraform_init(temp_dir)
            if not init_result["success"]:
                return init_result
            
            validate_result = self._terraform_validate(temp_dir)
            return validate_result
    
    def format_output(self, result: Dict) -> str:
        """Format validation output for display"""
        if result.get("valid"):
            return "✓ Terraform validation passed"
        else:
            output = "✗ Terraform validation failed\n"
            if result.get("stderr"):
                output += f"Error: {result['stderr']}"
            if result.get("error"):
                output += f"Error: {result['error']}"
            return output
