# -*- coding: utf-8 -*-
#
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MParentOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertParentService():
    def __init__(self, options: MParentOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "全親移植処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　センター回転移植: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.center_rotatation_flg) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_parent()

            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.model, self.options.output_path, False, False, [], None, 0, [])).write()

            logger.info("出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功")

            return result
        except MKilledException:
            return False
        except SizingException as se:
            logger.error("全親移植処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("全親移植処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 全親移植処理実行
    def convert_parent(self):
        motion = self.options.motion
        model = self.options.model

        root_bone_name = "全ての親"
        center_bone_name = "センター"
        center_parent_bone_name = "センター親"
        waist_bone_name = "腰"
        upper_bone_name = "上半身"
        lower_bone_name = "下半身"
        left_leg_ik_bone_name = "左足ＩＫ"
        right_leg_ik_bone_name = "右足ＩＫ"
        left_leg_ik_parent_bone_name = "左足IK親"
        right_leg_ik_parent_bone_name = "右足IK親"

        # まずキー登録
        # for bone_name in [root_bone_name]:
        #     if bone_name in model.bones:
        #         prev_sep_fno = 0
        #         fnos = motion.get_bone_fnos(root_bone_name, center_bone_name, waist_bone_name, upper_bone_name, lower_bone_name, \
        #                                     left_leg_ik_bone_name, right_leg_ik_bone_name, center_parent_bone_name, \
        #                                     left_leg_ik_parent_bone_name, right_leg_ik_parent_bone_name)
        #         for fno in fnos:
        #             bf = motion.calc_bf(bone_name, fno)
        #             motion.regist_bf(bf, bone_name, fno)

        #             if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
        #                 logger.info("-- %sフレーム目:終了(%s％)【準備 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
        #                 prev_sep_fno = fno // 2000

        for bone_name in [center_bone_name]:
            if bone_name in model.bones:
                prev_sep_fno = 0
                fno = 0
                fnos = motion.get_bone_fnos(bone_name, root_bone_name)

                for fno in fnos:
                    bf = motion.calc_bf(bone_name, fno)
                    motion.regist_bf(bf, bone_name, fno)
            
                    if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                        logger.count(f"【準備 - {bone_name}】", fno, fnos)
                        prev_sep_fno = fno // 2000

                logger.count(f"【準備 - {bone_name}】", fno, fnos)

        if self.options.center_rotatation_flg:
            for bone_name in [center_bone_name, upper_bone_name, lower_bone_name]:
                if bone_name in model.bones:
                    prev_sep_fno = 0
                    fno = 0
                    fnos = motion.get_bone_fnos(bone_name, center_bone_name, root_bone_name)

                    for fno in fnos:
                        bf = motion.calc_bf(bone_name, fno)
                        motion.regist_bf(bf, bone_name, fno)

                        if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                            logger.count(f"【準備 - {bone_name}】", fno, fnos)
                            prev_sep_fno = fno // 2000
                    
                    logger.count(f"【準備 - {bone_name}】", fno, fnos)

        for bone_name in [right_leg_ik_bone_name, left_leg_ik_bone_name]:
            if bone_name in model.bones:
                prev_sep_fno = 0
                fno = 0
                fnos = motion.get_bone_fnos(bone_name, root_bone_name, left_leg_ik_parent_bone_name, right_leg_ik_parent_bone_name)

                for fno in fnos:
                    bf = motion.calc_bf(bone_name, fno)
                    motion.regist_bf(bf, bone_name, fno)
            
                    if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                        logger.count(f"【準備 - {bone_name}】", fno, fnos)
                        prev_sep_fno = fno // 2000
                
                logger.count(f"【準備 - {bone_name}】", fno, fnos)

        logger.info("移植開始", decoration=MLogger.DECORATION_LINE)

        # センターの移植
        for bone_name in [center_bone_name]:
            if bone_name in model.bones:
                prev_sep_fno = 0
                fno = 0
                links = model.create_link_2_top_one(bone_name, is_defined=False)
                fnos = motion.get_bone_fnos(bone_name, root_bone_name)

                # 移植
                for fno in fnos:
                    root_bf = motion.calc_bf(root_bone_name, fno)
                    center_parent_bf = motion.calc_bf(center_parent_bone_name, fno)

                    bf = motion.calc_bf(bone_name, fno)
                    # logger.info("f: %s, prev bf.position: %s", fno, bf.position)

                    # relative_3ds_dic = MServiceUtils.calc_relative_position(model, links, motion, fno)
                    # [logger.info("R %s", v.to_log()) for v in relative_3ds_dic]
                    global_3ds_dic = MServiceUtils.calc_global_pos(model, links, motion, fno)
                    bone_global_pos = global_3ds_dic[bone_name]
                    # [logger.info("G %s: %s", k, v.to_log()) for k, v in global_3ds_dic.items()]
                    # logger.info("f: %s, bone_global_pos: %s", fno, bone_global_pos)

                    # グローバル位置からの差(センター親があった場合、それも加味して入れてしまう)
                    bf.position = bone_global_pos - model.bones[bone_name].position
                    # logger.info("f: %s, bf.position: %s", fno, bf.position)

                    # 回転の吸収
                    bf.rotation = root_bf.rotation * center_parent_bf.rotation * bf.rotation

                    motion.regist_bf(bf, bone_name, fno)

                    if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                        logger.count(f"【移植 - {bone_name}】", fno, fnos)
                        prev_sep_fno = fno // 2000

                logger.count(f"【移植 - {bone_name}】", fno, fnos)

        # 足IKの移植
        for bone_name, parent_bone_name in [(right_leg_ik_bone_name, right_leg_ik_parent_bone_name), (left_leg_ik_bone_name, left_leg_ik_parent_bone_name)]:
            if bone_name in model.bones:
                prev_sep_fno = 0
                fno = 0
                links = model.create_link_2_top_one(bone_name, is_defined=False)
                fnos = motion.get_bone_fnos(bone_name, root_bone_name)

                # 移植
                for fno in fnos:
                    root_bf = motion.calc_bf(root_bone_name, fno)
                    leg_ik_parent_bf = motion.calc_bf(parent_bone_name, fno)

                    bf = motion.calc_bf(bone_name, fno)
                    global_3ds_dic = MServiceUtils.calc_global_pos(model, links, motion, fno)
                    bone_global_pos = global_3ds_dic[bone_name]

                    # グローバル位置からの差(足IK親があった場合、それも加味して入れてしまう)
                    bf.position = bone_global_pos - model.bones[bone_name].position

                    # 回転
                    bf.rotation = root_bf.rotation * leg_ik_parent_bf.rotation * bf.rotation

                    motion.regist_bf(bf, bone_name, fno)

                    if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                        logger.count(f"【移植 - {bone_name}】", fno, fnos)
                        prev_sep_fno = fno // 2000

                logger.count(f"【移植 - {bone_name}】", fno, fnos)

        # 全ての親削除
        if root_bone_name in motion.bones:
            del motion.bones[root_bone_name]

        # センター親削除
        if center_parent_bone_name in motion.bones:
            del motion.bones[center_parent_bone_name]

        # 足IK親削除
        if left_leg_ik_parent_bone_name in motion.bones:
            del motion.bones[left_leg_ik_parent_bone_name]
        if right_leg_ik_parent_bone_name in motion.bones:
            del motion.bones[right_leg_ik_parent_bone_name]

        # logger.info("center_rotatation_flg: %s", self.options.center_rotatation_flg)

        if self.options.center_rotatation_flg:
            # センター→上半身・下半身の移植
            prev_sep_fno = 0
            fno = 0
            fnos = motion.get_bone_fnos(upper_bone_name, lower_bone_name, center_bone_name)
            for fno in fnos:
                center_bf = motion.calc_bf(center_bone_name, fno)
                waist_bf = motion.calc_bf(waist_bone_name, fno)
                upper_bf = motion.calc_bf(upper_bone_name, fno)
                lower_bf = motion.calc_bf(lower_bone_name, fno)

                center_links = model.create_link_2_top_one(center_bone_name, is_defined=False)
                lower_links = model.create_link_2_top_one(lower_bone_name, is_defined=False)

                # 一旦移動量を保持
                center_global_3ds_dic = MServiceUtils.calc_global_pos(model, lower_links, motion, fno, limit_links=center_links)

                # 回転移植
                upper_bf.rotation = center_bf.rotation * waist_bf.rotation * upper_bf.rotation
                motion.regist_bf(upper_bf, upper_bone_name, fno)

                lower_bf.rotation = center_bf.rotation * waist_bf.rotation * lower_bf.rotation
                motion.regist_bf(lower_bf, lower_bone_name, fno)

                # 腰クリア
                if waist_bone_name in model.bones:
                    waist_bf.rotation = MQuaternion()
                    motion.regist_bf(waist_bf, waist_bone_name, fno)

                # センター回転クリア
                center_bf.rotation = MQuaternion()
                # 移動を下半身ベースで再計算
                center_bf.position = center_global_3ds_dic[lower_bone_name] - model.bones[lower_bone_name].position
                motion.regist_bf(center_bf, center_bone_name, fno)

                if fno // 1000 > prev_sep_fno and fnos[-1] > 0:
                    logger.count("【移植 - 上半身・下半身】", fno, fnos)
                    prev_sep_fno = fno // 1000

            logger.count("【移植 - 上半身・下半身】", fno, fnos)

        logger.info("移植完了", decoration=MLogger.DECORATION_LINE)

        if self.options.remove_unnecessary_flg:
            futures = []

            with ThreadPoolExecutor(thread_name_prefix="remove", max_workers=self.options.max_workers) as executor:
                for bone_name in [center_bone_name, upper_bone_name, lower_bone_name, right_leg_ik_bone_name, left_leg_ik_bone_name]:
                    futures.append(executor.submit(self.remove_unnecessary_bf, bone_name))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False
        
        return True

    # 不要キー削除
    def remove_unnecessary_bf(self, bone_name: str):
        try:
            self.options.motion.remove_unnecessary_bf(0, bone_name, self.options.model.bones[bone_name].getRotatable(), \
                                                      self.options.model.bones[bone_name].getTranslatable())

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("全親移植処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
            return se
        except Exception as e:
            import traceback
            logger.critical("全親移植処理が意図せぬエラーで終了しました。\n\n%s", traceback.print_exc(), decoration=MLogger.DECORATION_BOX)
            raise e


