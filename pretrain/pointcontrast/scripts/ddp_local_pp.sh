# Implementation with Point Pillars

#!/bin/bash

export OUT_DIR=./tmp_out_dir

# python -m pudb ddp_train_pp.py \
python ddp_train_pp.py \
	net.model=PointPillarsPC \
	net.conv1_kernel_size=3 \
	opt.lr=0.1 \
	opt.max_iter=60000 \
	data.dataset=ScanNetMatchPairDataset \
	data.voxel_size=0.025 \
	trainer.batch_size=4 \
	trainer.stat_freq=1 \
	trainer.lr_update_freq=250 \
	misc.num_gpus=1 \
	misc.npos=4096 \
	misc.nceT=0.4 \
	misc.out_dir=${OUT_DIR} \
	trainer.trainer=HardestContrastiveLossTrainer \
	data.dataset_root_dir='/dg-hl-fast/codes/PointContrast/pretrain/pointcontrast/example_dataset' \
	data.scannet_match_dir='/dg-hl-fast/codes/PointContrast/pretrain/pointcontrast/example_dataset/overlap-30-50p-subset.txt' \
	# trainer.trainer=PointNCELossTrainer \

# Notes
# Batch size - taken as 4 per gpu by PointContrast work