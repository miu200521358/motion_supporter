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

logger = MLogger(__name__, level=MLogger.INFO)


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
            service_data_txt = "{service_data_txt}　足首水平化: {target_legs}\n".format(service_data_txt=service_data_txt,
                                    target_legs=self.options.ankle_horizonal_flg) # noqa
            service_data_txt = "{service_data_txt}　かかと・つま先Y=0: {target_legs}\n".format(service_data_txt=service_data_txt,
                                    target_legs=self.options.ground_leg_flg) # noqa
            if len(self.options.target_legs) > 0:
                service_data_txt = "{service_data_txt}　接地固定設定: {target_legs}\n".format(service_data_txt=service_data_txt,
                                        target_legs=(len(self.options.target_legs) > 0)) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 足首水平設定がある場合、足首水平化
            if self.options.ankle_horizonal_flg:
                self.prepare_ankle_horizonal()

            # 接地設定がある場合、接地設定
            if self.options.ground_leg_flg:
                self.prepare_ground()
            elif len(self.options.target_legs) > 0:
                self.prepare_ground2()
            
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
    
    # 足首の水平化
    def prepare_ankle_horizonal(self):
        logger.info("初期足首水平化", decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        # グルーブに値が入ってる場合、Yはグルーブに入れる
        center_x_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_x_bone_name = "センターMX"

        center_y_bone_name = "センター"
        if motion.is_active_bones("グルーブ"):
            center_y_bone_name = "グルーブ"
        elif not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_y_bone_name = "グルーブMY"

        center_z_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMZ"):
            center_z_bone_name = "センターMZ"

        # 足首角度
        for direction in ["右", "左"]:
            prev_sep_fno = 0

            # 足FK末端までのリンク
            # toe_fk_links = model.create_link_2_top_one(f"{direction}つま先実体", is_defined=False)
            ankle_fk_links = model.create_link_2_top_one(f"{direction}足首", is_defined=False)
            
            # 足首から先を固定で付与する
            if f"{direction}足底実体" in model.bones:
                ankle_fk_links.append(model.bones[f"{direction}足底実体"])
            if f"{direction}足先EX" in model.bones:
                ankle_fk_links.append(model.bones[f"{direction}足先EX"])
            if f"{direction}つま先実体" in model.bones:
                ankle_fk_links.append(model.bones[f"{direction}つま先実体"])

            # 指定範囲内の足首キーフレを取得
            fnos = motion.get_bone_fnos(f"{direction}足首")

            for fidx, fno in enumerate(fnos):
                toe_bf = motion.calc_bf(f"{direction}足首", fno)

                if toe_bf.rotation == MQuaternion():
                    toe_fk_3ds, toe_fk_matrixs = MServiceUtils.calc_global_pos(model, ankle_fk_links, motion, fno, return_matrix=True)
                    toe_pos = toe_fk_3ds[f"{direction}つま先実体"]
                    sole_pos = toe_fk_3ds[f"{direction}足底実体"]

                    toe_slope_from_pos = toe_pos
                    toe_slope_to_pos = MVector3D(toe_pos.x(), sole_pos.y(), toe_pos.z())

                    toe_slope_from_local_pos = toe_fk_matrixs[f"{direction}足底実体"].inverted() * toe_slope_from_pos
                    toe_slope_to_local_pos = toe_fk_matrixs[f"{direction}足底実体"].inverted() * toe_slope_to_pos

                    # 足首角度を調整する
                    toe_bf.rotation = MQuaternion.rotationTo(toe_slope_from_local_pos, toe_slope_to_local_pos)
                    motion.regist_bf(toe_bf, toe_bf.name, fno)

                if fno // 500 > prev_sep_fno:
                    logger.count(f"【初期足首水平化（{direction}）】", fno, fnos)
                    prev_sep_fno = fno // 500
            
    # 足ＩＫの接地準備
    def prepare_ground(self):
        logger.info("足ＩＫ接地", decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        # 足FK末端までのリンク
        right_fk_links = model.create_link_2_top_one("右つま先実体", is_defined=False)
        left_fk_links = model.create_link_2_top_one("左つま先実体", is_defined=False)

        # グルーブに値が入ってる場合、Yはグルーブに入れる
        center_x_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_x_bone_name = "センターMX"

        center_y_bone_name = "センター"
        if motion.is_active_bones("グルーブ"):
            center_y_bone_name = "グルーブ"
        elif not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_y_bone_name = "グルーブMY"

        center_z_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMZ"):
            center_z_bone_name = "センターMZ"

        # 指定範囲内の足FKキーフレを取得
        fnos = motion.get_bone_fnos("左足", "左ひざ", "左足首", "右足", "右ひざ", "右足首", "下半身", center_x_bone_name, center_y_bone_name, center_z_bone_name)

        # センター調整
        prev_sep_fno = 0
        for fidx, fno in enumerate(fnos):
            right_fk_3ds = MServiceUtils.calc_global_pos(model, right_fk_links, motion, fno)
            right_toe_pos = right_fk_3ds["右つま先実体"]
            right_sole_pos = right_fk_3ds["右足底実体"]

            left_fk_3ds = MServiceUtils.calc_global_pos(model, left_fk_links, motion, fno)
            left_toe_pos = left_fk_3ds["左つま先実体"]
            left_sole_pos = left_fk_3ds["左足底実体"]

            min_y = min(right_sole_pos.y(), left_sole_pos.y(), right_toe_pos.y(), left_toe_pos.y())

            # Y位置を調整する
            center_y_bf = motion.calc_bf(center_y_bone_name, fno)
            center_y_bf.position.setY(center_y_bf.position.y() - min_y)
            motion.regist_bf(center_y_bf, center_y_bone_name, fno)

            if fno // 500 > prev_sep_fno:
                logger.count("【足ＩＫ接地】", fno, fnos)
                prev_sep_fno = fno // 500
        
    # 足ＩＫの接地準備
    def prepare_ground2(self):
        logger.info("足ＩＫ接地固定", decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        # 足FK末端までのリンク
        right_fk_links = model.create_link_2_top_one("右つま先実体", is_defined=False)
        left_fk_links = model.create_link_2_top_one("左つま先実体", is_defined=False)

        # グルーブに値が入ってる場合、Yはグルーブに入れる
        center_x_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_x_bone_name = "センターMX"

        center_y_bone_name = "センター"
        if motion.is_active_bones("グルーブ"):
            center_y_bone_name = "グルーブ"
        elif not motion.is_active_bones("センター") and motion.is_active_bones("センターMX"):
            center_y_bone_name = "グルーブMY"

        center_z_bone_name = "センター"
        if not motion.is_active_bones("センター") and motion.is_active_bones("センターMZ"):
            center_z_bone_name = "センターMZ"

        # 指定範囲内の足FKキーフレを取得
        fnos = motion.get_bone_fnos("左足", "左ひざ", "左足首", "右足", "右ひざ", "右足首", "下半身", center_x_bone_name, center_y_bone_name, center_z_bone_name)

        target_legs = {}
        for lidx, (fromv, tov, ground_leg) in enumerate(self.options.target_legs):
            for fno in fnos:
                if fromv <= fno <= tov:
                    target_legs[fno] = ground_leg

        # # まずキー登録
        # prev_sep_fno = 0
        # for fidx, fno in enumerate(fnos):
        #     center_x_bf = motion.calc_bf(center_x_bone_name, fno)
        #     motion.regist_bf(center_x_bf, center_x_bone_name, fno)

        #     if center_x_bone_name != center_y_bone_name:
        #         center_y_bf = motion.calc_bf(center_y_bone_name, fno)
        #         motion.regist_bf(center_y_bf, center_y_bone_name, fno)

        #     if center_x_bone_name != center_z_bone_name:
        #         center_z_bf = motion.calc_bf(center_z_bone_name, fno)
        #         motion.regist_bf(center_z_bf, center_z_bone_name, fno)

        #     if fno // 1000 > prev_sep_fno:
        #         logger.count("【足ＩＫ接地準備①】", fno, fnos)
        #         prev_sep_fno = fno // 1000

        # センター調整
        for lidx, (fromv, tov, ground_leg) in enumerate(self.options.target_legs):
            fix_x_pos = MVector3D()
            fix_z_pos = MVector3D()
            for fidx, fno in enumerate(fnos):
                if fromv <= fno <= tov:
                    right_fk_3ds = MServiceUtils.calc_global_pos(model, right_fk_links, motion, fno)
                    right_toe_pos = right_fk_3ds["右つま先実体"]
                    right_sole_pos = right_fk_3ds["右足底実体"]

                    left_fk_3ds = MServiceUtils.calc_global_pos(model, left_fk_links, motion, fno)
                    left_toe_pos = left_fk_3ds["左つま先実体"]
                    left_sole_pos = left_fk_3ds["左足底実体"]

                    target_leg_x = None
                    target_leg_z = None
                    target_leg_ys = []
                    if ground_leg == "右かかと":
                        target_leg_x = right_sole_pos.x()
                        target_leg_ys.append(right_sole_pos.y())
                        target_leg_z = right_sole_pos.z()
                    elif ground_leg == "左かかと":
                        target_leg_x = left_sole_pos.x()
                        target_leg_ys.append(left_sole_pos.y())
                        target_leg_z = left_sole_pos.z()
                    elif ground_leg == "右つま先":
                        target_leg_x = right_toe_pos.x()
                        target_leg_ys.append(right_toe_pos.y())
                        target_leg_z = right_toe_pos.z()
                    elif ground_leg == "左つま先":
                        target_leg_x = left_toe_pos.x()
                        target_leg_ys.append(left_toe_pos.y())
                        target_leg_z = left_toe_pos.z()

                    min_y = min(target_leg_ys)

                    # Y位置を調整する
                    center_y_bf = motion.calc_bf(center_y_bone_name, fno)
                    center_y_bf.position.setY(center_y_bf.position.y() - min_y)
                    motion.regist_bf(center_y_bf, center_y_bone_name, fno)

                    # XZを固定する
                    if fix_x_pos == MVector3D() and fix_z_pos == MVector3D():
                        # 最初のキーフレで固定する
                        fix_x_pos = MVector3D(target_leg_x, 0, 0)
                        fix_z_pos = MVector3D(0, 0, target_leg_z)

                    if center_x_bone_name == center_z_bone_name:
                        # 固定位置からの差分
                        diff_pos = (fix_x_pos + fix_z_pos) - MVector3D(target_leg_x, 0, target_leg_z)

                        # 差分を加算
                        center_bf = motion.calc_bf(center_x_bone_name, fno)
                        center_bf.position += diff_pos
                        motion.regist_bf(center_bf, center_x_bone_name, fno)
                    else:
                        # 固定位置からの差分
                        diff_x_pos = fix_x_pos - MVector3D(target_leg_x, 0, 0)
                        diff_z_pos = fix_z_pos - MVector3D(0, 0, target_leg_z)

                        # X差分を加算
                        center_x_bf = motion.calc_bf(center_x_bone_name, fno)
                        center_x_bf.position += diff_x_pos
                        motion.regist_bf(center_x_bf, center_x_bone_name, fno)

                        # Z差分を加算
                        center_z_bf = motion.calc_bf(center_z_bone_name, fno)
                        center_z_bf.position += diff_z_pos
                        motion.regist_bf(center_z_bf, center_z_bone_name, fno)

            logger.info(f"-- 【足ＩＫ接地固定】{fromv} ～ {tov} F：{ground_leg}")

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
        fno = 0
        for fno in fnos:
            bf = motion.calc_bf(leg_ik_bone_name, fno)
            motion.regist_bf(bf, leg_ik_bone_name, fno)

            if fno // 1000 > prev_sep_fno and fnos[-1] > 0:
                logger.count(f"【準備 - {leg_ik_bone_name}】", fno, fnos)
                prev_sep_fno = fno // 1000
        
        logger.info("準備完了　【%s足ＩＫ】", direction, decoration=MLogger.DECORATION_LINE)

        ik_parent_name = ik_links.get(leg_ik_bone_name, offset=-1).name

        # 足IKの移植
        prev_sep_fno = 0

        # 移植
        fno = 0
        for fno in fnos:
            leg_fk_3ds_dic = MServiceUtils.calc_global_pos(model, fk_links, motion, fno)
            _, leg_ik_matrixs = MServiceUtils.calc_global_pos(model, ik_links, motion, fno, return_matrix=True)

            # 足首の角度がある状態での、つま先までのグローバル位置
            leg_toe_fk_3ds_dic = MServiceUtils.calc_global_pos(model, toe_fk_links, motion, fno)

            # IKの親から見た相対位置
            leg_ik_parent_matrix = leg_ik_matrixs[ik_parent_name]

            bf = motion.calc_bf(leg_ik_bone_name, fno)
            # 足ＩＫの位置は、足ＩＫの親から見た足首のローカル位置（足首位置マイナス）
            bf.position = leg_ik_parent_matrix.inverted() * (leg_fk_3ds_dic[ankle_bone_name] - (model.bones[ankle_bone_name].position - model.bones[ik_parent_name].position))
            bf.rotation = MQuaternion()

            # 一旦足ＩＫの位置が決まった時点で登録
            motion.regist_bf(bf, leg_ik_bone_name, fno)
            # 足ＩＫ回転なし状態でのつま先までのグローバル位置
            leg_ik_3ds_dic, leg_ik_matrisxs = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, fno, return_matrix=True)
            [logger.debug("f: %s, leg_ik_3ds_dic[%s]: %s", fno, k, v.to_log()) for k, v in leg_ik_3ds_dic.items()]

            # つま先のローカル位置
            ankle_child_initial_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * leg_ik_3ds_dic[toe_ik_bone_name]
            ankle_child_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * leg_toe_fk_3ds_dic[ankle_child_bone_name]

            logger.debug("f: %s, ankle_child_initial_local_pos: %s", fno, ankle_child_initial_local_pos.to_log())
            logger.debug("f: %s, ankle_child_local_pos: %s", fno, ankle_child_local_pos.to_log())

            # 足ＩＫの回転は、足首から見たつま先の方向
            bf.rotation = MQuaternion.rotationTo(ankle_child_initial_local_pos, ankle_child_local_pos)
            logger.debug("f: %s, ik_rotation: %s", fno, bf.rotation.toEulerAngles4MMD().to_log())

            motion.regist_bf(bf, leg_ik_bone_name, fno)

            if fno // 500 > prev_sep_fno and fnos[-1] > 0:
                logger.count(f"【足ＩＫ変換 - {leg_ik_bone_name}】", fno, fnos)
                prev_sep_fno = fno // 500

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



