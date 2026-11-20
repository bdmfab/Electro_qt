#!/usr/bin/env bash
# Build the Linux program: run from the project folder.  Needs python3 (3.10+) with venv.
set -e
python3 -m venv build_venv
. build_venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean packaging/electro_qt.spec
VER=$(python -c "import electro; print(electro.__version__)")
tar -C dist -czf "dist/Electro_qt-$VER-linux.tar.gz" Electro_qt
echo
echo "Program folder: dist/Electro_qt   (run dist/Electro_qt/Electro_qt)"
echo "Hand-out file:  dist/Electro_qt-$VER-linux.tar.gz   (unpack anywhere, run Electro_qt)"
echo "Needs on the target machine:  sudo apt install libxcb-cursor0"
