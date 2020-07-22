# -*- coding: utf-8 -*-
#
import os
import sys
import argparse

from mmd.PmxReader import PmxReader
from mmd.VmdReader import VmdReader
from mmd.VpdReader import VpdReader
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MFileUtils
from utils.MException import SizingException
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class MOptionsDataSet():

    def __init__(self, motion, org_model=None, rep_model=None, output_vmd_path=None, detail_stance_flg=0, twist_flg=0, morph_list=[], \
                 camera_org_model=None, camera_offset_y=0, selected_stance_details=[]):
        self.motion = motion
        self.org_model = org_model
        self.rep_model = rep_model
        self.output_vmd_path = output_vmd_path
        self.detail_stance_flg = detail_stance_flg
        self.twist_flg = twist_flg
        self.morph_list = morph_list
        self.camera_org_model = camera_org_model
        self.camera_offset_y = camera_offset_y
        self.selected_stance_details = selected_stance_details

        self.org_motion = self.motion.copy()
        self.test_params = None
        self.full_arms = False

        # 本来の足IKの比率
        self.original_xz_ratio = 1
        self.original_y_ratio = 1

        # 実際に計算に使う足IKの比率
        self.xz_ratio = 1
        self.y_ratio = 1


class MParentOptions():

    def __init__(self, version_name, logging_level, max_workers, motion, model, output_path, monitor, is_file, outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.output_path = output_path
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


class MNoiseOptions():

    def __init__(self, version_name, logging_level, max_workers, motion, model, noise_size, copy_cnt, output_path, monitor, is_file, outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.copy_cnt = copy_cnt
        self.noise_size = noise_size
        self.output_path = output_path
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers
