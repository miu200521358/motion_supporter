# -*- coding: utf-8 -*-
#
import math
import numpy as np
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MNoiseOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertNoiseService():
    def __init__(self, options: MNoiseOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "ゆらぎ複製処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　ゆらぎの大きさ: {noise_size}\n".format(service_data_txt=service_data_txt,
                                    noise_size=self.options.noise_size) # noqa
            service_data_txt = "{service_data_txt}　複製数: {copy_cnt}体\n".format(service_data_txt=service_data_txt,
                                    copy_cnt=self.options.copy_cnt) # noqa
            service_data_txt = "{service_data_txt}　指ゆらぎ: {finger_noise}\n".format(service_data_txt=service_data_txt,
                                    finger_noise=self.options.finger_noise_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            futures = []

            with ThreadPoolExecutor(thread_name_prefix="move", max_workers=self.options.max_workers) as executor:
                for copy_no in range(self.options.copy_cnt):
                    # やる気係数を適用する場合、シード生成
                    seed = np.random.randint(85, 115) / 100 if self.options.motivation_flg else 1
                    futures.append(executor.submit(self.convert_noise, copy_no, seed))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False

            return True
        except MKilledException:
            return False
        except SizingException as se:
            logger.error("ゆらぎ複製処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("ゆらぎ複製処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # ゆらぎ複製処理実行
    def convert_noise(self, copy_no: int, seed: float):
        logger.info("ゆらぎ複製　【No.%s】", (copy_no + 1), decoration=MLogger.DECORATION_LINE)

        # データをコピーしてそっちを弄る
        motion = self.options.motion.copy()

        for bone_name in motion.bones.keys():
            if not self.options.finger_noise_flg and "指" in bone_name:
                logger.info("-- 指スキップ【No.%s - %s】", copy_no + 1, bone_name)
                continue

            fnos = motion.get_bone_fnos(bone_name)
            prev_fno = 0
            prev_sep_fno = 0

            # 事前に細分化
            self.prepare_split_stance(motion, bone_name)
            logger.info("-- 準備完了【No.%s - %s】", copy_no + 1, bone_name)

            for fno in fnos:
                bf = motion.bones[bone_name][fno]
                org_bf = self.options.motion.calc_bf(bone_name, fno)

                # 移動
                if bf.position != MVector3D():
                    prev_org_bf = self.options.motion.calc_bf(bone_name, prev_fno)

                    if org_bf.position == prev_org_bf.position and fno > 0:
                        bf.position = motion.calc_bf(bone_name, prev_fno).position
                    else:
                        # 0だったら動かさない
                        if round(org_bf.position.x(), 1) != 0:
                            if self.options.motivation_flg:
                                bf.position.setX(bf.position.x() * seed + (0.5 - np.random.rand()) * (self.options.noise_size / 10))
                            else:
                                bf.position.setX(bf.position.x() + (0.5 - np.random.rand()) * (self.options.noise_size / 10))
                        if round(org_bf.position.y(), 1) != 0 and "足ＩＫ" not in bone_name:
                            # 足ＩＫのＹは動かさない
                            if self.options.motivation_flg:
                                if org_bf.position.y() < 0:
                                    # Yはオリジナルがマイナスの場合は、マイナスのみに動かす
                                    bf.position.setY(bf.position.y() * seed + (0 - np.random.rand()) * (self.options.noise_size / 10))
                                elif org_bf.position.y() > 0:
                                    bf.position.setY(bf.position.y() * seed + (0.5 - np.random.rand()) * (self.options.noise_size / 10))
                            else:
                                bf.position.setY(bf.position.y() + (0.5 - np.random.rand()) * (self.options.noise_size / 10))
                        if round(org_bf.position.z(), 1) != 0:
                            if self.options.motivation_flg:
                                bf.position.setZ(bf.position.z() * seed + (0.5 - np.random.rand()) * (self.options.noise_size / 10))
                            else:
                                bf.position.setZ(bf.position.z() + (0.5 - np.random.rand()) * (self.options.noise_size / 10))

                        # 移動補間曲線
                        for (bz_idx1, bz_idx2, bz_idx3, bz_idx4) in [MBezierUtils.MX_x1_idxs, MBezierUtils.MX_y1_idxs, MBezierUtils.MX_x2_idxs, MBezierUtils.MX_y2_idxs, \
                                                                     MBezierUtils.MY_x1_idxs, MBezierUtils.MY_y1_idxs, MBezierUtils.MY_x2_idxs, MBezierUtils.MY_y2_idxs, \
                                                                     MBezierUtils.MZ_x1_idxs, MBezierUtils.MZ_y1_idxs, MBezierUtils.MZ_x2_idxs, MBezierUtils.MZ_y2_idxs]:
                            noise_interpolation = bf.interpolation[bz_idx1] + math.ceil((0.5 - np.random.rand()) * self.options.noise_size)
                            bf.interpolation[bz_idx1] = bf.interpolation[bz_idx2] = bf.interpolation[bz_idx3] = bf.interpolation[bz_idx4] = int(noise_interpolation)
                
                # 回転
                euler = bf.rotation.toEulerAngles()
                # 回転は元が0であっても動かす(足は除く)
                if "足" not in bone_name and "ひざ" not in bone_name and "足首" not in bone_name:
                    if self.options.motivation_flg:
                        euler.setX(euler.x() * seed + (0.5 - np.random.rand()) * self.options.noise_size)
                        euler.setY(euler.y() * seed + (0.5 - np.random.rand()) * self.options.noise_size)
                        euler.setZ(euler.z() * seed + (0.5 - np.random.rand()) * self.options.noise_size)
                    else:
                        euler.setX(euler.x() + (0.5 - np.random.rand()) * self.options.noise_size)
                        euler.setY(euler.y() + (0.5 - np.random.rand()) * self.options.noise_size)
                        euler.setZ(euler.z() + (0.5 - np.random.rand()) * self.options.noise_size)
                bf.rotation = MQuaternion.fromEulerAngles(euler.x(), euler.y(), euler.z())

                # 回転補間曲線
                for (bz_idx1, bz_idx2, bz_idx3, bz_idx4) in [MBezierUtils.R_x1_idxs, MBezierUtils.R_y1_idxs, MBezierUtils.R_x2_idxs, MBezierUtils.R_y2_idxs]:
                    noise_interpolation = bf.interpolation[bz_idx1] + math.ceil((0.5 - np.random.rand()) * self.options.noise_size)

                    bf.interpolation[bz_idx1] = bf.interpolation[bz_idx2] = bf.interpolation[bz_idx3] = bf.interpolation[bz_idx4] = int(noise_interpolation)
                
                # 前回fno保持
                prev_fno = fno

                if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                    logger.count(f"【No.{copy_no + 1} - {bone_name}】", fno, fnos)
                    prev_sep_fno = fno // 2000

        output_path = self.options.output_path.replace("nxxx", "n{0:03d}".format(copy_no + 1))
        output_path = output_path.replace("axxx", "a{0:+03d}".format(int(seed * 100) - 100))

        # 最後に出力
        VmdWriter(MOptionsDataSet(motion, None, self.options.model, output_path, False, False, [], None, 0, [])).write()

        logger.info("出力成功: %s", os.path.basename(output_path), decoration=MLogger.DECORATION_BOX)

        return True

    # スタンス用細分化
    def prepare_split_stance(self, motion: VmdMotion, target_bone_name: str):
        fnos = motion.get_bone_fnos(target_bone_name)

        for fidx, fno in enumerate(fnos):
            if fidx == 0:
                continue

            prev_bf = motion.bones[target_bone_name][fnos[fidx - 1]]
            bf = motion.bones[target_bone_name][fno]
            diff_degree = abs(prev_bf.rotation.toDegree() - bf.rotation.toDegree())

            if diff_degree >= 150:
                # 回転量が約150度以上の場合、半分に分割しておく
                half_fno = prev_bf.fno + round((bf.fno - prev_bf.fno) / 2)

                if prev_bf.fno < half_fno < bf.fno:
                    # キーが追加できる状態であれば、追加
                    half_bf = motion.calc_bf(target_bone_name, half_fno)
                    motion.regist_bf(half_bf, target_bone_name, half_fno)


