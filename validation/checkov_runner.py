import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

class CheckovRunner:
    """Run Checkov security scanning on Terraform code"""
    
    def __init__(self):
        self.checkov_path = self._find_checkov()
    
    def _find_checkov(self) -> str:
        """Find checkov executable"""
        try:
            result = subprocess.run(["which", "checkov"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return "checkov"
    
    def scan(self, terraform_code: str, framework: str = "terraform") -> Dict:
        """Scan Terraform code with Checkov"""
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write terraform code
            main_tf = Path(temp_dir) / "main.tf"
            main_tf.write_text(terraform_code)
            
            # Run checkov
            result = self._run_checkov(temp_dir, framework)
            
            return result
    
    def scan_directory(self, directory: str, framework: str = "terraform") -> Dict:
        """Scan a directory with Checkov"""
        return self._run_checkov(directory, framework)
    
    def _run_checkov(self, target: str, framework: str) -> Dict:
        """Run checkov command"""
        try:
            cmd = [
                self.checkov_path,
                "-f", target,
                "-f", framework,
                "--output", "json",
                "--quiet",
                "--compact",
                "--soft-fail"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            # Parse output
            if result.stdout:
                try:
                    import json
                    output_data = json.loads(result.stdout)
                    
                    passed_checks = output_data.get("results", {}).get("passed_checks", 0)
                    failed_checks = output_data.get("results", {}).get("failed_checks", [])
                    
                    return {
                        "success": True,
                        "passed": passed_checks,
                        "failed": len(failed_checks),
                        "failed_checks": failed_checks,
                        "returncode": result.returncode,
                        "compliant": len(failed_checks) == 0
                    }
                except json.JSONDecodeError:
                    pass
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "compliant": result.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Checkov scan timed out",
                "compliant": False
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "compliant": False
            }
    
    def scan_with_config(
        self,
        terraform_code: str,
        checkov_config: Dict
    ) -> Dict:
        """Scan with custom Checkov configuration"""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write terraform code
            main_tf = Path(temp_dir) / "main.tf"
            main_tf.write_text(terraform_code)
            
            # Write checkov config
            config_file = Path(temp_dir) / ".checkov.yaml"
            import yaml
            config_file.write_text(yaml.dump(checkov_config))
            
            # Run checkov with config
            result = self._run_checkov(temp_dir, "terraform")
            
            return result
    
    def get_failed_check_summary(self, result: Dict) -> List[Dict]:
        """Get summary of failed checks"""
        failed_checks = result.get("failed_checks", [])
        
        summary = []
        for check in failed_checks:
            summary.append({
                "check_id": check.get("check_id"),
                "severity": check.get("severity"),
                "description": check.get("check", {}).get("name"),
                "resource": check.get("resource"),
                "file_path": check.get("file_path")
            })
        
        return summary
    
    def filter_by_severity(self, result: Dict, min_severity: str = "MEDIUM") -> Dict:
        """Filter results by minimum severity level"""
        severity_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        min_index = severity_order.index(min_severity)
        
        failed_checks = result.get("failed_checks", [])
        filtered = [
            check for check in failed_checks
            if severity_order.index(check.get("severity", "LOW")) >= min_index
        ]
        
        return {
            **result,
            "failed_checks": filtered,
            "failed": len(filtered)
        }
