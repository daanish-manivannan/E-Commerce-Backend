import os

template_path = "gateway/kong.template.yml"
output_path = "gateway/kong.yml"

with open(template_path, "r", encoding="utf-8") as f:
    content = f.read()

secret = os.environ.get("JWT_SECRET", "test_secret_for_kong_123")
content = content.replace("${KONG_JWT_SECRET}", secret)

with open(output_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)

print("Generated kong.yml")
