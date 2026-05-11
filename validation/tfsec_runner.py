import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

class TfsecRunner:
    """Run tfsec security scanning on Terraform code"""
    
    def __init__(self):
        self.tfsec_path = self._find_tfsec()
    
    def _find_tfsec(self) -> str:
        """Find tfsec executable"""
        try:
            result = subprocess.run(["which", "tfsec"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return "tfsec"
    
    def scan(self, terraform_code: str) -> Dict:
        """Scan Terraform code with tfsec"""
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write terraform code
            main_tf = Path(temp_dir) / "main.tf"
            main_tf.write_text(terraform_code)
            
            # Run tfsec
            result = self._run_tfsec(temp_dir)
            
            return result
    
    def scan_directory(self, directory: str) -> Dict:
        """Scan a directory with tfsec"""
        return self._run_tfsec(directory)
    
    def _run_tfsec(self, target: str) -> Dict:
        """Run tfsec command"""
        try:
            cmd = [
                self.tfsec_path,
                target,
                "--format", "json",
                "--soft-fail",
                "--exclude", "AWS001"  # Example exclusion
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
                    
                    return {
                        "success": True,
                        "passed_checks": output_data.get("passed_checks", 0),
                        "failed_checks": output_data.get("failed_checks", []),
                        "total_checks": output_data.get("total_checks", 0),
                        "returncode": result.returncode,
                        "compliant": len(output_data.get("failed_checks", [])) == 0
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
                "error": "tfsec scan timed out",
                "compliant": False
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "compliant": False
            }
    
    def scan_with_severity(self, terraform_code: str, min_severity: str = "MEDIUM") -> Dict:
        """Scan with minimum severity threshold"""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write terraform code
            main_tf = Path(temp_dir) / "main.tf"
            main_tf.write_text(terraform_code)
            
            # Run tfsec with severity filter
            cmd = [
                self.tfsec_path,
                temp_dir,
                "--format", "json",
                "--soft-fail",
                "--minimum-severity", min_severity
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.stdout:
                    try:
                        import json
                        output_data = json.loads(result.stdout)
                        
                        return {
                            "success": True,
                            "failed_checks": output_data.get("failed_checks", []),
                            "compliant": len(output_data.get("failed_checks", [])) == 0
                        }
                    except json.JSONDecodeError:
                        pass
                
                return {
                    "success": result.returncode == 0,
                    "compliant": result.returncode == 0
                }
                
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": "tfsec scan timed out",
                    "compliant": False
                }
    
    def get_severity_summary(self, result: Dict) -> Dict:
        """Get summary of results by severity"""
        failed_checks = result.get("failed_checks", [])
        
        summary = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0
        }
        
        for check in failed_checks:
            severity = check.get("severity", "LOW")
            summary[severity] = summary.get(severity, 0) + 1
        
        return summary
    
    def get_failed_check_details(self, result: Dict) -> List[Dict]:
        """Get details of failed checks"""
        failed_checks = result.get("failed_checks", [])
        
        details = []
        for check in failed_checks:
            details.append({
                "rule_id": check.get("rule_id"),
                "severity": check.get("severity"),
                "description": check.get("description"),
                "resource": check.get("resource"),
                "location": check.get("location"),
                "impact": check.get("impact"),
                "resolution": check.get("resolution")
            })
        
        return details
