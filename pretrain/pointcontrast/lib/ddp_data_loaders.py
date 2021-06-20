# Copyright (c) Facebook, Inc. and its affiliates.
# 
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import logging
import random
import torch
import torch.utils.data
import numpy as np
import glob
import os
import copy
from tqdm import tqdm
from scipy.linalg import expm, norm

import lib.transforms as t

import MinkowskiEngine as ME

import open3d as o3d

from torch.utils.data.sampler import RandomSampler
from lib.data_sampler import DistributedInfSampler

from pcdet.datasets.carla.mdls.carla_mdls_dataset import CarlaMdlsDataset
from pcdet.config import cfg, cfg_from_list, cfg_from_yaml_file, log_config_to_file

def make_open3d_point_cloud(xyz, color=None):
  pcd = o3d.geometry.PointCloud()
  pcd.points = o3d.utility.Vector3dVector(xyz)
  if color is not None:
    pcd.colors = o3d.utility.Vector3dVector(color)
  return pcd


def get_matching_indices(source, target, trans, search_voxel_size, K=None):
  source_copy = copy.deepcopy(source)
  target_copy = copy.deepcopy(target)
  source_copy.transform(trans)
  pcd_tree = o3d.geometry.KDTreeFlann(target_copy)

  match_inds = []
  for i, point in enumerate(source_copy.points):
    [_, idx, _] = pcd_tree.search_radius_vector_3d(point, search_voxel_size)
    if K is not None:
      idx = idx[:K]
    for j in idx:
      match_inds.append((i, j))
  return match_inds


def default_collate_pair_fn(list_data):
  xyz0, xyz1, coords0, coords1, feats0, feats1, matching_inds, trans = list(
      zip(*list_data))
  xyz_batch0, coords_batch0, feats_batch0 = [], [], []
  xyz_batch1, coords_batch1, feats_batch1 = [], [], []
  matching_inds_batch, trans_batch, len_batch = [], [], []

  batch_id = 0
  curr_start_inds = np.zeros((1, 2))
  for batch_id, _ in enumerate(coords0):

    N0 = coords0[batch_id].shape[0]
    N1 = coords1[batch_id].shape[0]

    # Move batchids to the beginning
    xyz_batch0.append(torch.from_numpy(xyz0[batch_id]))
    coords_batch0.append(
        torch.cat((torch.ones(N0, 1).int() * batch_id, 
                   torch.from_numpy(coords0[batch_id]).int()), 1))
    feats_batch0.append(torch.from_numpy(feats0[batch_id]))

    xyz_batch1.append(torch.from_numpy(xyz1[batch_id]))
    coords_batch1.append(
        torch.cat((torch.ones(N1, 1).int() * batch_id, 
                   torch.from_numpy(coords1[batch_id]).int()), 1))
    feats_batch1.append(torch.from_numpy(feats1[batch_id]))

    trans_batch.append(torch.from_numpy(trans[batch_id]))
    
    # in case 0 matching
    if len(matching_inds[batch_id]) == 0:
      matching_inds[batch_id].extend([0, 0])
    
    matching_inds_batch.append(
        torch.from_numpy(np.array(matching_inds[batch_id]) + curr_start_inds))
    len_batch.append([N0, N1])

    # Move the head
    curr_start_inds[0, 0] += N0
    curr_start_inds[0, 1] += N1

  # Concatenate all lists
  xyz_batch0 = torch.cat(xyz_batch0, 0).float()
  coords_batch0 = torch.cat(coords_batch0, 0).int()
  feats_batch0 = torch.cat(feats_batch0, 0).float()
  xyz_batch1 = torch.cat(xyz_batch1, 0).float()
  coords_batch1 = torch.cat(coords_batch1, 0).int()
  feats_batch1 = torch.cat(feats_batch1, 0).float()
  trans_batch = torch.cat(trans_batch, 0).float()
  matching_inds_batch = torch.cat(matching_inds_batch, 0).int()
  return {
      'pcd0': xyz_batch0,
      'pcd1': xyz_batch1,
      'sinput0_C': coords_batch0,
      'sinput0_F': feats_batch0,
      'sinput1_C': coords_batch1,
      'sinput1_F': feats_batch1,
      'correspondences': matching_inds_batch,
      'T_gt': trans_batch,
      'len_batch': len_batch,
  }

cfg_file_path = '/dg-hl-fast/codes/OpenPCDet/tools/cfgs/carla_mdls_models/pointpillar_point_contrast.yaml'
cfg_from_yaml_file(cfg_file_path, cfg)
carla_dataset_instance = CarlaMdlsDataset(cfg.DATA_CONFIG, cfg.CLASS_NAMES)

def default_collate_pair_fn_pp(list_data):
  xyz0, xyz1, coords0, coords1, feats0, feats1, matching_inds, trans, batch_dict_0, batch_dict_1 = list(
      zip(*list_data))
  xyz_batch0, coords_batch0, feats_batch0 = [], [], []
  xyz_batch1, coords_batch1, feats_batch1 = [], [], []
  matching_inds_batch, trans_batch, len_batch = [], [], []

  bd_0 = carla_dataset_instance.collate_batch(batch_dict_0)
  bd_1 = carla_dataset_instance.collate_batch(batch_dict_1)

  batch_id = 0
  curr_start_inds = np.zeros((1, 2))
  for batch_id, _ in enumerate(coords0):

    N0 = coords0[batch_id].shape[0]
    N1 = coords1[batch_id].shape[0]

    # Move batchids to the beginning
    xyz_batch0.append(torch.from_numpy(xyz0[batch_id]))
    coords_batch0.append(
        torch.cat((torch.ones(N0, 1).int() * batch_id, 
                   torch.from_numpy(coords0[batch_id]).int()), 1))
    feats_batch0.append(torch.from_numpy(feats0[batch_id]))

    xyz_batch1.append(torch.from_numpy(xyz1[batch_id]))
    coords_batch1.append(
        torch.cat((torch.ones(N1, 1).int() * batch_id, 
                   torch.from_numpy(coords1[batch_id]).int()), 1))
    feats_batch1.append(torch.from_numpy(feats1[batch_id]))

    trans_batch.append(torch.from_numpy(trans[batch_id]))
    
    # in case 0 matching
    if len(matching_inds[batch_id]) == 0:
      matching_inds[batch_id].extend([0, 0])
    
    matching_inds_batch.append(
        torch.from_numpy(np.array(matching_inds[batch_id]) + curr_start_inds))
    len_batch.append([N0, N1])

    # Move the head
    curr_start_inds[0, 0] += N0
    curr_start_inds[0, 1] += N1

  # Concatenate all lists
  xyz_batch0 = torch.cat(xyz_batch0, 0).float()
  coords_batch0 = torch.cat(coords_batch0, 0).int()
  feats_batch0 = torch.cat(feats_batch0, 0).float()
  xyz_batch1 = torch.cat(xyz_batch1, 0).float()
  coords_batch1 = torch.cat(coords_batch1, 0).int()
  feats_batch1 = torch.cat(feats_batch1, 0).float()
  trans_batch = torch.cat(trans_batch, 0).float()
  matching_inds_batch = torch.cat(matching_inds_batch, 0).int()
  return {
      'pcd0': xyz_batch0,
      'pcd1': xyz_batch1,
      'sinput0_C': coords_batch0,
      'sinput0_F': feats_batch0,
      'sinput1_C': coords_batch1,
      'sinput1_F': feats_batch1,
      'correspondences': matching_inds_batch,
      'T_gt': trans_batch,
      'len_batch': len_batch,
      'bd_0': bd_0,
      'bd_1': bd_1
  }


# Rotation matrix along axis with angle theta
def M(axis, theta):
  return expm(np.cross(np.eye(3), axis / norm(axis) * theta))

def sample_random_rts(pcd, randg, rotation_range=360, scale_range=None, translation_range=None):
  # first minus mean (centering), then rotation 360 degrees
  T_rot = np.eye(4)
  R = M(randg.rand(3) - 0.5, rotation_range * np.pi / 180.0 * (randg.rand(1) - 0.5))
  T_rot[:3, :3] = R
  T_rot[:3, 3] = R.dot(-np.mean(pcd, axis=0))
  
  T_scale = np.eye(4)
  if scale_range:
      scale = np.random.uniform(*scale_range)
      np.fill_diagonal(T_scale[:3, :3], scale)
  
  T_translation = np.eye(4)
  if translation_range:
    offside = np.random.uniform(*translation_range, 3)
    T_translation[:3, 3] = offside

  return T_rot @ T_scale @ T_translation

def sample_random_trans(pcd, randg, rotation_range=360):
  T = np.eye(4)
  R = M(randg.rand(3) - 0.5, rotation_range * np.pi / 180.0 * (randg.rand(1) - 0.5))
  T[:3, :3] = R
  T[:3, 3] = R.dot(-np.mean(pcd, axis=0))
  return T

class ScanNetMatchPairDataset(torch.utils.data.Dataset):
  def __init__(self,
               phase,
               transform=None,
               random_rotation=True,
               random_scale=True,
               manual_seed=False,
               config=None):
    self.phase = phase
    self.files = []
    self.data_objects = []
    self.transform = transform
    self.voxel_size = config.data.voxel_size
    self.matching_search_voxel_size = \
        config.data.voxel_size * config.trainer.positive_pair_search_voxel_size_multiplier

    self.random_scale = random_scale
    self.min_scale = config.trainer.min_scale
    self.max_scale = config.trainer.max_scale
    self.random_rotation = random_rotation
    self.rotation_range = config.trainer.rotation_range
    self.randg = np.random.RandomState()
    
    if manual_seed:
      self.reset_seed()
    
    self.root_filelist = root = config.data.scannet_match_dir
    self.root = config.data.dataset_root_dir
    logging.info(f"Loading the subset {phase} from {root}")
    if phase == "train":
       fname_txt = os.path.join(self.root, self.root_filelist)
       with open(fname_txt) as f:
         content = f.readlines()
       fnames = [x.strip().split() for x in content]
       for fname in fnames:
         self.files.append([fname[0], fname[1]])
    else:
        raise NotImplementedError

  def reset_seed(self, seed=0):
    logging.info(f"Resetting the data loader seed to {seed}")
    self.randg.seed(seed)

  def apply_transform(self, pts, trans):
    R = trans[:3, :3]
    T = trans[:3, 3]
    pts = pts @ R.T + T
    return pts
  
  def __len__(self):
    return len(self.files)

  def __getitem__(self, idx):
    file0 = os.path.join(self.root, self.files[idx][0])
    file1 = os.path.join(self.root, self.files[idx][1])
    data0 = np.load(file0)
    data1 = np.load(file1)
    xyz0 = data0["pcd"]
    xyz1 = data1["pcd"]
    
    #dummy color
    color0 = np.ones((xyz0.shape[0], 3))
    color1 = np.ones((xyz1.shape[0], 3))

    matching_search_voxel_size = self.matching_search_voxel_size

    if self.random_scale and random.random() < 0.95:
      scale = self.min_scale + \
          (self.max_scale - self.min_scale) * random.random()
      matching_search_voxel_size *= scale
      xyz0 = scale * xyz0
      xyz1 = scale * xyz1

    if self.random_rotation:
      T0 = sample_random_trans(xyz0, self.randg, self.rotation_range)
      T1 = sample_random_trans(xyz1, self.randg, self.rotation_range)
      trans = T1 @ np.linalg.inv(T0)

      xyz0 = self.apply_transform(xyz0, T0)
      xyz1 = self.apply_transform(xyz1, T1)
    else:
      trans = np.identity(4)

    # Voxelization
    sel0 = ME.utils.sparse_quantize(xyz0 / self.voxel_size, return_index=True)
    sel1 = ME.utils.sparse_quantize(xyz1 / self.voxel_size, return_index=True)

    # Make point clouds using voxelized points
    pcd0 = make_open3d_point_cloud(xyz0)
    pcd1 = make_open3d_point_cloud(xyz1)

    # Select features and points using the returned voxelized indices
    pcd0.colors = o3d.utility.Vector3dVector(color0[sel0])
    pcd1.colors = o3d.utility.Vector3dVector(color1[sel1])
    pcd0.points = o3d.utility.Vector3dVector(np.array(pcd0.points)[sel0])
    pcd1.points = o3d.utility.Vector3dVector(np.array(pcd1.points)[sel1])
    # Get matches
    matches = get_matching_indices(pcd0, pcd1, trans, matching_search_voxel_size)
    # Get features
    npts0 = len(pcd0.colors)
    npts1 = len(pcd1.colors)

    feats_train0, feats_train1 = [], []

    feats_train0.append(np.ones((npts0, 3)))
    feats_train1.append(np.ones((npts1, 3)))

    feats0 = np.hstack(feats_train0)
    feats1 = np.hstack(feats_train1)

    # Get coords
    xyz0 = np.array(pcd0.points)
    xyz1 = np.array(pcd1.points)

    coords0 = np.floor(xyz0 / self.voxel_size)
    coords1 = np.floor(xyz1 / self.voxel_size)

    if self.transform:
      coords0, feats0 = self.transform(coords0, feats0)
      coords1, feats1 = self.transform(coords1, feats1)

    return (xyz0, xyz1, coords0, coords1, feats0, feats1, matches, trans)

class PCCarlaMDLSDataset(torch.utils.data.Dataset):
  def __init__(self,
               phase,
               transform=None,
               random_rotation=True,
               random_scale=True,
               manual_seed=False,
               config=None):

    self.pcdet_carla_mdls_dataset = carla_dataset_instance

    self.phase = phase
    self.files = []
    self.data_objects = []
    self.transform = transform
    self.voxel_size = config.data.voxel_size
    self.matching_search_voxel_size = \
        config.data.voxel_size * config.trainer.positive_pair_search_voxel_size_multiplier

    self.random_scale = random_scale
    self.min_scale = config.trainer.min_scale
    self.max_scale = config.trainer.max_scale
    self.random_rotation = random_rotation
    self.rotation_range = config.trainer.rotation_range
    self.randg = np.random.RandomState()
    
    if manual_seed:
      self.reset_seed()
    
    self.root_filelist = root = config.data.scannet_match_dir
    self.root = config.data.dataset_root_dir
    logging.info(f"Loading the subset {phase} from {root}")
    if phase == "train":
       fname_txt = os.path.join(self.root, self.root_filelist)
       with open(fname_txt) as f:
         content = f.readlines()
       fnames = [x.strip().split() for x in content]
       for fname in fnames:
         self.files.append([fname[0], fname[1]])
    else:
        raise NotImplementedError

  def reset_seed(self, seed=0):
    logging.info(f"Resetting the data loader seed to {seed}")
    self.randg.seed(seed)

  def apply_transform(self, pts, trans):
    R = trans[:3, :3]
    T = trans[:3, 3]
    pts = pts @ R.T + T
    return pts
  
  def __len__(self):
    # return len(self.files)
    return len(self.pcdet_carla_mdls_dataset)

  def __getitem__(self, idx):

    # Get data from pcdet's dataset class
    data_idx_0 = self.pcdet_carla_mdls_dataset[idx]
    xyz0 = data_idx_0['points'] # Shape - (123186, 3)
    xyz1 = np.copy(xyz0)

    # file0 = os.path.join(self.root, self.files[idx][0])
    # file1 = os.path.join(self.root, self.files[idx][1])
    # data0 = np.load(file0)
    # data1 = np.load(file1)
    # xyz0 = data0["pcd"]
    # xyz1 = data1["pcd"]
    
    #dummy color
    color0 = np.ones((xyz0.shape[0], 3))
    color1 = np.ones((xyz0.shape[0], 3))

    matching_search_voxel_size = self.matching_search_voxel_size

    if self.random_scale and random.random() < 0.95:
      scale = self.min_scale + \
          (self.max_scale - self.min_scale) * random.random()
      matching_search_voxel_size *= scale
      xyz0 = scale * xyz0
      xyz1 = scale * xyz1

    if self.random_rotation:
      # T0 = sample_random_trans(xyz0, self.randg, self.rotation_range)
      T0 = np.identity(4)
      T1 = sample_random_trans(xyz0, self.randg, self.rotation_range)
      trans = T1 @ np.linalg.inv(T0)

      # xyz0 = self.apply_transform(xyz0, T0)
      xyz1 = self.apply_transform(xyz1, T1)
    else:
      trans = np.identity(4)

    input_dict = {
      'points': xyz1,
      'frame_id': data_idx_0['frame_id'],
      'calib': data_idx_0['calib'],
      'gt_names': data_idx_0['gt_names'],
      'gt_boxes': data_idx_0['gt_boxes']
    }
    data_idx_1 = self.pcdet_carla_mdls_dataset.prepare_data(data_dict=input_dict)

    # Removing gt_names again to resolve error in collating fn
    for data_item in [data_idx_0, data_idx_1]:
      if 'gt_names' in data_item.keys():
        del data_item['gt_names']

    # Voxelization
    sel0 = ME.utils.sparse_quantize(xyz0 / self.voxel_size, return_index=True)
    sel1 = ME.utils.sparse_quantize(xyz1 / self.voxel_size, return_index=True)

    # Make point clouds using voxelized points
    pcd0 = make_open3d_point_cloud(xyz0)
    pcd1 = make_open3d_point_cloud(xyz1)

    # Select features and points using the returned voxelized indices
    pcd0.colors = o3d.utility.Vector3dVector(color0[sel0])
    pcd1.colors = o3d.utility.Vector3dVector(color1[sel1])
    pcd0.points = o3d.utility.Vector3dVector(np.array(pcd0.points)[sel0])
    pcd1.points = o3d.utility.Vector3dVector(np.array(pcd1.points)[sel1])
    # Get matches
    matches = get_matching_indices(pcd0, pcd1, trans, matching_search_voxel_size)
    # Get features
    npts0 = len(pcd0.colors)
    npts1 = len(pcd1.colors)

    feats_train0, feats_train1 = [], []

    feats_train0.append(np.ones((npts0, 3)))
    feats_train1.append(np.ones((npts1, 3)))

    feats0 = np.hstack(feats_train0)
    feats1 = np.hstack(feats_train1)

    # Get coords
    xyz0 = np.array(pcd0.points)
    xyz1 = np.array(pcd1.points)

    coords0 = np.floor(xyz0 / self.voxel_size)
    coords1 = np.floor(xyz1 / self.voxel_size)

    if self.transform:
      coords0, feats0 = self.transform(coords0, feats0)
      coords1, feats1 = self.transform(coords1, feats1)

    return (xyz0, xyz1, coords0, coords1, feats0, feats1, matches, trans, data_idx_0, data_idx_1)

  def __getitem_old__(self, idx):
    file0 = os.path.join(self.root, self.files[idx][0])
    file1 = os.path.join(self.root, self.files[idx][1])
    data0 = np.load(file0)
    data1 = np.load(file1)
    xyz0 = data0["pcd"]
    xyz1 = data1["pcd"]
    
    #dummy color
    color0 = np.ones((xyz0.shape[0], 3))
    color1 = np.ones((xyz1.shape[0], 3))

    matching_search_voxel_size = self.matching_search_voxel_size

    if self.random_scale and random.random() < 0.95:
      scale = self.min_scale + \
          (self.max_scale - self.min_scale) * random.random()
      matching_search_voxel_size *= scale
      xyz0 = scale * xyz0
      xyz1 = scale * xyz1

    if self.random_rotation:
      T0 = sample_random_trans(xyz0, self.randg, self.rotation_range)
      T1 = sample_random_trans(xyz1, self.randg, self.rotation_range)
      trans = T1 @ np.linalg.inv(T0)

      xyz0 = self.apply_transform(xyz0, T0)
      xyz1 = self.apply_transform(xyz1, T1)
    else:
      trans = np.identity(4)

    # Voxelization
    sel0 = ME.utils.sparse_quantize(xyz0 / self.voxel_size, return_index=True)
    sel1 = ME.utils.sparse_quantize(xyz1 / self.voxel_size, return_index=True)

    # Make point clouds using voxelized points
    pcd0 = make_open3d_point_cloud(xyz0)
    pcd1 = make_open3d_point_cloud(xyz1)

    # Select features and points using the returned voxelized indices
    pcd0.colors = o3d.utility.Vector3dVector(color0[sel0])
    pcd1.colors = o3d.utility.Vector3dVector(color1[sel1])
    pcd0.points = o3d.utility.Vector3dVector(np.array(pcd0.points)[sel0])
    pcd1.points = o3d.utility.Vector3dVector(np.array(pcd1.points)[sel1])
    # Get matches
    matches = get_matching_indices(pcd0, pcd1, trans, matching_search_voxel_size)
    # Get features
    npts0 = len(pcd0.colors)
    npts1 = len(pcd1.colors)

    feats_train0, feats_train1 = [], []

    feats_train0.append(np.ones((npts0, 3)))
    feats_train1.append(np.ones((npts1, 3)))

    feats0 = np.hstack(feats_train0)
    feats1 = np.hstack(feats_train1)

    # Get coords
    xyz0 = np.array(pcd0.points)
    xyz1 = np.array(pcd1.points)

    coords0 = np.floor(xyz0 / self.voxel_size)
    coords1 = np.floor(xyz1 / self.voxel_size)

    if self.transform:
      coords0, feats0 = self.transform(coords0, feats0)
      coords1, feats1 = self.transform(coords1, feats1)

    return (xyz0, xyz1, coords0, coords1, feats0, feats1, matches, trans)

ALL_DATASETS = [ScanNetMatchPairDataset, PCCarlaMDLSDataset]
dataset_str_mapping = {d.__name__: d for d in ALL_DATASETS}


def make_data_loader(config, batch_size, num_threads=0):

  if config.data.dataset not in dataset_str_mapping.keys():
    logging.error(f'Dataset {config.data.dataset}, does not exists in ' +
                  ', '.join(dataset_str_mapping.keys()))

  Dataset = dataset_str_mapping[config.data.dataset]

  transforms = []
  use_random_rotation = config.trainer.use_random_rotation
  use_random_scale = config.trainer.use_random_scale
  transforms += [t.Jitter()]

  dset = Dataset(
      phase="train",
      transform=t.Compose(transforms),
      random_scale=use_random_scale,
      random_rotation=use_random_rotation,
      config=config)
  collate_pair_fn = default_collate_pair_fn_pp
  batch_size = batch_size // config.misc.num_gpus

  if config.misc.num_gpus > 1:
    sampler = DistributedInfSampler(dset)
  else:
    sampler = None
  
  loader = torch.utils.data.DataLoader(
      dset,
      batch_size=batch_size,
      shuffle=False if sampler else True,
      num_workers=num_threads,
      collate_fn=collate_pair_fn,
      pin_memory=False,
      sampler=sampler,
      drop_last=True)

  return loader
