# Copyright (c) Facebook, Inc. and its affiliates.
# 
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import model.res16unet as res16unet
import model.pointpillars as pointpillars

MODELS = []


def add_models(module):
  MODELS.extend([getattr(module, a) for a in dir(module) if 'Net' in a])

add_models(res16unet)
add_models(pointpillars)

def get_models():
  '''Returns a tuple of sample models.'''
  return MODELS

def load_model(name):
  '''Creates and returns an instance of the model given its class name.
  '''
  all_models = get_models()
  mdict = {model.__name__: model for model in all_models}
  exceptions = ['PointPillarsPC']
  if not (name in mdict or name in exceptions):
    print('Invalid model index. Options are:')
    for model in all_models:
      print('\t* {}'.format(model.__name__))
    return None
  
  if name in exceptions:
    if name == 'PointPillarsPC':
      from pointcontrast.model.pointpillars import model as pointpillars_instantiated_model
      print("Loading PointPillarsPC : ", pointpillars_instantiated_model)
      NetClass = pointpillars_instantiated_model
  else:
    NetClass = mdict[name]

  return NetClass
