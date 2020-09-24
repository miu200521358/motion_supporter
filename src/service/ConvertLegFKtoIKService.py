# -*- coding: utf-8 -*-
#
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MLegFKtoIKOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertLegFKtoIKService():
    def __init__(self, options: MLegFKtoIKOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "足ＩＫ変換処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            futures = []

            with ThreadPoolExecutor(thread_name_prefix="leffk", max_workers=self.options.max_workers) as executor:
                futures.append(executor.submit(self.convert_leg_fk2ik, "右"))
                futures.append(executor.submit(self.convert_leg_fk2ik, "左"))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False
            
            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.model, self.options.output_path, False, False, [], None, 0, [])).write()

            logger.info("出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功")

            return True
        except MKilledException:
            return False
        except SizingException as se:
            logger.error("足ＩＫ変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("足ＩＫ変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 足ＩＫ変換処理実行
    def convert_leg_fk2ik(self, direction: str):
        logger.info("足ＩＫ変換　【%s足ＩＫ】", direction, decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        leg_ik_bone_name = "{0}足ＩＫ".format(direction)
        toe_ik_bone_name = "{0}つま先ＩＫ".format(direction)
        leg_bone_name = "{0}足".format(direction)
        knee_bone_name = "{0}ひざ".format(direction)
        ankle_bone_name = "{0}足首".format(direction)

        # 足FK末端までのリンク
        fk_links = model.create_link_2_top_one(ankle_bone_name, is_defined=False)
        # 足IK末端までのリンク
        ik_links = model.create_link_2_top_one(leg_ik_bone_name, is_defined=False)
        # つま先IK末端までのリンク
        toe_ik_links = model.create_link_2_top_one(toe_ik_bone_name, is_defined=False)
        # つま先（足首の子ボーン）の名前
        ankle_child_bone_name = model.bone_indexes[model.bones[toe_ik_bone_name].ik.target_index]
        # つま先末端までのリンク
        toe_fk_links = model.create_link_2_top_one(ankle_child_bone_name, is_defined=False)

        fnos = motion.get_bone_fnos(leg_bone_name, knee_bone_name, ankle_bone_name)

        # まずキー登録
        prev_sep_fno = 0
        for fno in fnos:
            bf = motion.calc_bf(leg_ik_bone_name, fno)
            motion.regist_bf(bf, leg_ik_bone_name, fno)

            if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【準備 - %s】", fno, round((fno / fnos[-1]) * 100, 3), leg_ik_bone_name)
                prev_sep_fno = fno // 2000
        
        if len(fnos) > 0:
            logger.info("-- %sフレーム目:終了(%s％)【準備 - %s】", fnos[-1], round((fnos[-1] / fnos[-1]) * 100, 3), leg_ik_bone_name)

        logger.info("準備完了　【%s足ＩＫ】", direction, decoration=MLogger.DECORATION_LINE)

        ik_parent_name = ik_links.get(leg_ik_bone_name, offset=-1).name

        # 足IKの移植
        prev_sep_fno = 0

        # 移植
        for fno in fnos:
            leg_fk_3ds_dic = MServiceUtils.calc_global_pos(model, fk_links, motion, fno)
            _, leg_ik_matrixs = MServiceUtils.calc_global_pos(model, ik_links, motion, fno, return_matrix=True)

            # IKの親から見た相対位置
            leg_ik_parent_matrix = leg_ik_matrixs[ik_parent_name]

            bf = motion.calc_bf(leg_ik_bone_name, fno)
            # 足ＩＫの位置は、足ＩＫの親から見た足首のローカル位置（足首位置マイナス）
            bf.position = leg_ik_parent_matrix.inverted() * (leg_fk_3ds_dic[ankle_bone_name] - (model.bones[ankle_bone_name].position - model.bones[ik_parent_name].position))

            # 足首の角度がある状態での、つま先までのグローバル位置
            leg_toe_fk_3ds_dic = MServiceUtils.calc_global_pos(model, toe_fk_links, motion, fno)

            # 一旦足ＩＫの位置が決まった時点で登録
            motion.regist_bf(bf, leg_ik_bone_name, fno)
            # 足ＩＫ回転なし状態でのつま先までのグローバル位置
            leg_ik_3ds_dic, leg_ik_matrisxs = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, fno, return_matrix=True)

            # つま先のローカル位置
            ankle_child_initial_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * leg_ik_3ds_dic[toe_ik_bone_name]
            ankle_child_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * leg_toe_fk_3ds_dic[ankle_child_bone_name]

            # 足ＩＫの回転は、足首から見たつま先の方向
            bf.rotation = MQuaternion.rotationTo(ankle_child_initial_local_pos, ankle_child_local_pos)

            motion.regist_bf(bf, leg_ik_bone_name, fno)

            if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【足ＩＫ変換 - %s】", fno, round((fno / fnos[-1]) * 100, 3), leg_ik_bone_name)
                prev_sep_fno = fno // 2000

        if len(fnos) > 0:
            logger.info("-- %sフレーム目:終了(%s％)【足ＩＫ変換 - %s】", fnos[-1], round((fnos[-1] / fnos[-1]) * 100, 3), leg_ik_bone_name)

        logger.info("変換完了　【%s足ＩＫ】", direction, decoration=MLogger.DECORATION_LINE)

        # IKon
        for showik in self.options.motion.showiks:
            for ikf in showik.ik:
                if ikf.name == leg_ik_bone_name or ikf.name == toe_ik_bone_name:
                    ikf.onoff = 1

        # 不要キー削除処理
        if self.options.remove_unnecessary_flg:
            self.options.motion.remove_unnecessary_bf(0, leg_ik_bone_name, self.options.model.bones[leg_ik_bone_name].getRotatable(), \
                                                      self.options.model.bones[leg_ik_bone_name].getTranslatable())
        
        return True



