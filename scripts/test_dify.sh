#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/test_dify.sh <image_path>

DIFY_BASE=${DIFY_BASE:-https://api.dify.ai/v1}
DIFY_API_KEY=${DIFY_API_KEY:-app-mDDa4ZWe5VOe6TvPQvfpDFCI}
USER_ID=${USER_ID:-a1d9906b-6db6-431d-bd1f-8f5e3d53b8a1}
FILE_PATH=${1:-${FILE_PATH:-$HOME/Downloads/image.png}}

if [ ! -f "$FILE_PATH" ]; then
  echo "File not found: $FILE_PATH" >&2
  exit 1
fi

echo "Uploading $FILE_PATH ..."
FILE_ID=$(curl -s -X POST "$DIFY_BASE/files/upload" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -F "file=@${FILE_PATH};type=$(file --brief --mime-type "$FILE_PATH")" \
  -F "user=$USER_ID" | jq -r '.id')

if [ -z "$FILE_ID" ] || [ "$FILE_ID" = "null" ]; then
  echo "Upload failed." >&2
  exit 1
fi
echo "FILE_ID=$FILE_ID"

echo "Invoking workflow ..."
curl -N -X POST "$DIFY_BASE/workflows/run" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{
  "inputs": {
    "product_name": "REDHUT Limpiador a vapor portátil con 12 accesorios, limpieza profunda para cocina, baño, hogar y automóvil",
    "shop_name": "REDHUT",
    "region": "MX",
    "language": "Spanish",
    "thumbnail": [
      { "transfer_method": "local_file", "upload_file_id": "$FILE_ID", "type": "image" }
    ]
  },
  "response_mode": "streaming",
  "user": "$USER_ID"
}
JSON
