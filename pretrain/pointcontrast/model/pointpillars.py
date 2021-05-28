import numpy as np

from pcdet.models import build_network, model_fn_decorator
from pcdet.config import cfg, cfg_from_list, cfg_from_yaml_file, log_config_to_file

cfg_file_path = '/dg-hl-fast/codes/OpenPCDet/tools/cfgs/carla_mdls_models/pointpillar_point_contrast.yaml'
cfg_from_yaml_file(cfg_file_path, cfg)

class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

voxel_size = cfg.DATA_CONFIG.DATA_PROCESSOR[2].VOXEL_SIZE
point_cloud_range = np.array(cfg.DATA_CONFIG.POINT_CLOUD_RANGE)
grid_size = (point_cloud_range[3:6] - point_cloud_range[0:3]) / np.array(voxel_size)
grid_size = np.round(grid_size).astype(np.int64)

train_set_dataset_mock = {
    "point_feature_encoder": dotdict({'num_point_features': 3 }), #TODO: Try reading it from config
    "grid_size": grid_size,
    "point_cloud_range": point_cloud_range,
    "voxel_size": voxel_size,
    "class_names": cfg.CLASS_NAMES
}
train_set_dataset_mock = dotdict(train_set_dataset_mock)

model = build_network(model_cfg=cfg.MODEL, num_class=len(cfg.CLASS_NAMES), dataset=train_set_dataset_mock)

if __name__ == '__main__':
    print("Hello World")