# -*- coding: utf-8 -*-
#
import os
import sys
import argparse

from libcpp cimport  list, str, dict, float, int

from mmd.PmxData cimport PmxModel, Bone
from mmd.VmdData cimport VmdMotion, VmdBoneFrame
from module.MParams cimport BoneLinks # noqa
from module.MMath cimport MRect, MVector2D, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa

from mmd.PmxReader import PmxReader
from mmd.VmdReader import VmdReader
from mmd.VpdReader import VpdReader
from mmd.PmxData import Vertex, Material, Morph, DisplaySlot, RigidBody, Joint # noqa
from mmd.VmdData import VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from utils import MFileUtils
from utils.MException import SizingException
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)

cdef class MOptionsDataSet():
    cdef public VmdMotion motion
    cdef public PmxModel org_model
    cdef public PmxModel rep_model
    cdef public str output_vmd_path
    cdef public bint detail_stance_flg
    cdef public bint twist_flg
    cdef public list morph_list
    cdef public PmxModel camera_org_model
    cdef public float camera_offset_y
    cdef public list selected_stance_details

    cdef public VmdMotion org_motion
    cdef public dict test_params
    cdef public bint full_arms

    # 本来の足IKの比率
    cdef public float original_xz_ratio
    cdef public float original_y_ratio

    # 実際に計算に使う足IKの比率
    cdef public float xz_ratio
    cdef public float y_ratio


cdef class MParentOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public str output_path
    cdef public bint center_rotatation_flg
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MNoiseOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public str output_path
    cdef public int noise_size 
    cdef public int copy_cnt
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers
    cdef public bint finger_noise_flg
    cdef public bint motivation_flg


cdef class MArmIKtoFKOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel ik_model
    cdef public PmxModel fk_model
    cdef public list target_bones
    cdef public str output_path
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MArmTwistOffOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public list target_bones
    cdef public str output_path
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MMultiSplitOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public list target_bones
    cdef public str output_path
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MMultiJoinOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public list target_bones
    cdef public str output_path
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MLegFKtoIKOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public bint ground_leg_flg
    cdef public bint ankle_horizonal_flg
    cdef public float leg_error_tolerance
    cdef public str output_path
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers


cdef class MSmoothOptions():
    cdef public str version_name
    cdef public int logging_level
    cdef public int max_workers
    cdef public VmdMotion motion
    cdef public PmxModel model
    cdef public str output_path
    cdef public int loop_cnt
    cdef public int interpolation
    cdef public list bone_list
    cdef public bint remove_unnecessary_flg
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime


cdef class MMorphConditionOptions:
    cdef public str version_name
    cdef public int logging_level
    cdef public VmdMotion motion
    cdef public list target_morphs
    cdef public str output_path
    cdef public object monitor
    cdef public bint is_file
    cdef public str outout_datetime
    cdef public int max_workers

cdef c_smooth_parse(str version_name)




