# Validation

Security and schema validation for generated Terraform code.

## Components

- **terraform_validator.py** - Run `terraform validate` on generated code
- **hcl_parser.py** - Parse HCL/Terraform files using python-hcl2
- **schema_validator.py** - Validate schema and detect hallucinations
- **checkov_runner.py** - Run Checkov security scanning
- **tfsec_runner.py** - Run tfsec security scanning

## Usage

```python
from validation.terraform_validator import TerraformValidator
from validation.schema_validator import SchemaValidator
from validation.checkov_runner import CheckovRunner

# Terraform validation
tf_validator = TerraformValidator()
result = tf_validator.validate(terraform_code)

# Schema validation
schema_validator = SchemaValidator()
result = schema_validator.validate_schema(terraform_code, design_doc)

# Security scanning with Checkov
checkov = CheckovRunner()
result = checkov.scan(terraform_code)

# Security scanning with tfsec
tfsec = TfsecRunner()
result = tfsec.scan(terraform_code)
```

## Features

- **Terraform Validation**: Syntax and configuration validation
- **HCL Parsing**: Extract resources, modules, variables, outputs
- **Schema Validation**: Detect hallucinations and missing resources
- **Circular Dependency Detection**: Identify circular dependencies
- **Security Scanning**: Checkov and tfsec integration
- **Severity Filtering**: Filter results by severity level

## Requirements

- terraform (for terraform validate)
- checkov (for security scanning)
- tfsec (for security scanning)
- python-hcl2 (for HCL parsing)
