#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "  Merkezi Analiz Sunucusu başlatılıyor..."
echo ""

if ! command -v python3 &>/dev/null; then
  echo "  HATA: python3 bulunamadı."
  echo "  Mac'ine Xcode Command Line Tools kurman gerekebilir:"
  echo "  Terminal'e yaz: xcode-select --install"
  exit 1
fi

pip3 install -r requirements.txt -q
python3 app.py
