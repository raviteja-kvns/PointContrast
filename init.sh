pip install -r requirements.txt
export PYTHONPATH=/dg-hl-fast/codes/PointContrast/pretrain:$PYTHONPATH

# Other dependencies
apt-get update
apt-get upgrade
apt-get install -y libusb-1.0-0 ffmpeg libsm6 libxext6