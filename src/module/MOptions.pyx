# -*- coding: utf-8 -*-
#
import os
import sys
import argparse

from libcpp cimport  list, str, dict, float, int

from module.MParams cimport BoneLinks # noqa
from mmd.PmxData cimport PmxModel, Bone
from mmd.VmdData cimport VmdMotion, VmdBoneFrame
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


cdef class MOptionsDataSet:

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


cdef class MParentOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, str output_path, bint center_rotatation_flg, \
                 bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.output_path = output_path
        self.center_rotatation_flg = center_rotatation_flg
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MNoiseOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, int noise_size, int copy_cnt, \
                 bint finger_noise_flg, bint motivation_flg, str output_path, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.copy_cnt = copy_cnt
        self.finger_noise_flg = finger_noise_flg
        self.motivation_flg = motivation_flg
        self.noise_size = noise_size
        self.output_path = output_path
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MArmIKtoFKOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel ik_model, PmxModel fk_model, str output_path, \
                 bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.ik_model = ik_model
        self.fk_model = fk_model
        self.output_path = output_path
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MArmTwistOffOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, str output_path, \
                 bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.output_path = output_path
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MMultiSplitOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, list target_bones, str output_path, \
                 bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.target_bones = target_bones
        self.output_path = output_path
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MMultiJoinOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, list target_bones, str output_path, \
                 bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.target_bones = target_bones
        self.output_path = output_path
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers


cdef class MLegFKtoIKOptions:

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, list target_legs, bint ground_leg_flg, \
                 bint ankle_horizonal_flg, str output_path, bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.target_legs = target_legs
        self.ground_leg_flg = ground_leg_flg
        self.ankle_horizonal_flg = ankle_horizonal_flg
        self.output_path = output_path
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers



class MBlendOptions():

    def __init__(self, str version_name, int logging_level, PmxModel model, list eye_list, list eyebrow_list, list lip_list, list other_list, \
                 float min_value, float max_value, float inc_value):
        self.version_name = version_name
        self.logging_level = logging_level
        self.model = model
        self.eye_list = eye_list
        self.eyebrow_list = eyebrow_list
        self.lip_list = lip_list
        self.other_list = other_list
        self.min_value = min_value
        self.max_value = max_value
        self.inc_value = inc_value


cdef class MSmoothOptions():

    def __init__(self, str version_name, int logging_level, int max_workers, VmdMotion motion, PmxModel model, str output_path, \
                 int loop_cnt, int interpolation, list bone_list, bint remove_unnecessary_flg, object monitor, bint is_file, str outout_datetime):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion
        self.model = model
        self.output_path = output_path
        self.loop_cnt = loop_cnt
        self.interpolation = interpolation
        self.bone_list = bone_list
        self.remove_unnecessary_flg = remove_unnecessary_flg
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.max_workers = max_workers

    @classmethod
    def parse(cls, version_name: str):
        return c_smooth_parse(version_name)


cdef c_smooth_parse(str version_name):
    parser = argparse.ArgumentParser()
    parser.add_argument('--motion_path', dest='motion_path', help='input vmd', type=str)
    parser.add_argument('--model_path', dest='model_path', help='model_path', type=str)
    parser.add_argument('--loop_cnt', dest='loop_cnt', help='loop_cnt', type=int)
    parser.add_argument('--interpolation', dest='interpolation', help='interpolation', type=int)
    parser.add_argument("--bone_list", default=[], type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--verbose", type=int, default=20)

    args = parser.parse_args()

    # ログディレクトリ作成
    os.makedirs("log", exist_ok=True)

    MLogger.initialize(level=args.verbose, is_file=True)

    try:
        motion = VmdReader(args.motion_path).read_data()
        model = PmxReader(args.model_path).read_data()

        # 出力ファイルパス
        output_vmd_path = MFileUtils.get_output_smooth_vmd_path(motion.path, model.path, "", args.interpolation, args.loop_cnt, True)

        options = MSmoothOptions(\
            version_name=version_name, \
            logging_level=args.verbose, \
            motion=motion, \
            model=model, \
            output_path=output_vmd_path, \
            loop_cnt=args.loop_cnt, \
            interpolation=args.interpolation, \
            bone_list=args.bone_list, \
            monitor=sys.stdout, \
            is_file=True, \
            outout_datetime=logger.outout_datetime, \
            max_workers=1)

        return options
    except SizingException as se:
        logger.error("スムージング処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
    except Exception as e:
        logger.critical("スムージング処理が意図せぬエラーで終了しました。", e, decoration=MLogger.DECORATION_BOX)

