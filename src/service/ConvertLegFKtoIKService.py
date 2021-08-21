# -*- coding: utf-8 -*-
#
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import numpy as np

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
            service_data_txt = "{service_data_txt}　足首水平化: {ankle_horizonal_flg}\n".format(service_data_txt=service_data_txt,
                                    ankle_horizonal_flg=self.options.ankle_horizonal_flg) # noqa
            service_data_txt = "{service_data_txt}　かかと・つま先Y=0: {ground_leg_flg}\n".format(service_data_txt=service_data_txt,
                                    ground_leg_flg=self.options.ground_leg_flg) # noqa
            service_data_txt = "{service_data_txt}　足IKブレ固定: {leg_error_tolerance}\n".format(service_data_txt=service_data_txt,
                                    leg_error_tolerance=self.options.leg_error_tolerance) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # # 足首水平設定がある場合、足首水平化
            # if self.options.ankle_horizonal_flg:
            #     self.prepare_ankle_horizonal()

            # 接地設定がある場合、接地設定
            if self.options.ground_leg_flg:
                self.prepare_ground()

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
        min_ys = []
        for fidx, fno in enumerate(fnos):
            right_fk_3ds = MServiceUtils.calc_global_pos(model, right_fk_links, motion, fno)
            right_toe_pos = right_fk_3ds["右つま先実体"]
            right_sole_pos = right_fk_3ds["右足底実体"]

            left_fk_3ds = MServiceUtils.calc_global_pos(model, left_fk_links, motion, fno)
            left_toe_pos = left_fk_3ds["左つま先実体"]
            left_sole_pos = left_fk_3ds["左足底実体"]

            min_ys.append(right_sole_pos.y())
            min_ys.append(left_sole_pos.y())
            min_ys.append(right_toe_pos.y())
            min_ys.append(left_toe_pos.y())

            if fno // 500 > prev_sep_fno:
                logger.count("【足ＩＫ接地準備】", fno, fnos)
                prev_sep_fno = fno // 500

        # 中央の値は大体接地していると見なす
        median_leg_y = np.median(min_ys)
        logger.debug("接地: median: %s", median_leg_y)
        # # 中央上よりで調整
        # median_leg_y = np.median(np.array(min_ys)[min_ys > median_leg_y])
        # logger.debug("接地: median2: %s", median_leg_y)

        prev_sep_fno = 0
        for fidx, fno in enumerate(fnos):
            # Y位置を調整する
            center_y_bf = motion.calc_bf(center_y_bone_name, fno)
            center_y_bf.position.setY(center_y_bf.position.y() - median_leg_y)
            motion.regist_bf(center_y_bf, center_y_bone_name, fno)

            if fno // 500 > prev_sep_fno:
                logger.count("【足ＩＫ接地】", fno, fnos)
                prev_sep_fno = fno // 500

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
            if bf.position.y() < 0:
                bf.position.setY(0)
            bf.rotation = MQuaternion()

            # 一旦足ＩＫの位置が決まった時点で登録
            motion.regist_bf(bf, leg_ik_bone_name, fno)
            # 足ＩＫ回転なし状態でのつま先までのグローバル位置
            leg_ik_3ds_dic, leg_ik_matrisxs = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, fno, return_matrix=True)
            [logger.debug("f: %s, leg_ik_3ds_dic[%s]: %s", fno, k, v.to_log()) for k, v in leg_ik_3ds_dic.items()]

            # つま先のローカル位置
            toe_global_pos = leg_ik_3ds_dic[toe_ik_bone_name]
            ankle_child_initial_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * toe_global_pos
            ankle_child_global_pos = leg_toe_fk_3ds_dic[ankle_child_bone_name]
            ankle_child_local_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * ankle_child_global_pos
            ankle_horizonal_pos = leg_ik_matrisxs[leg_ik_bone_name].inverted() * MVector3D(ankle_child_global_pos.x(), model.bones[ankle_child_bone_name].position.y(), ankle_child_global_pos.z())

            ankle_slope = abs(MVector3D.dotProduct(ankle_horizonal_pos.normalized(), ankle_child_local_pos.normalized()))
            if (self.options.ankle_horizonal_flg and (ankle_slope > 0.95)) or toe_global_pos.y() < 0:
                logger.debug("f: %s, %s水平 %s ankle_child_local_pos: %s, ankle_horizonal_pos: %s", fno, direction, ankle_slope, ankle_child_local_pos.to_log(), ankle_horizonal_pos.to_log())
                # 大体水平の場合、地面に対して水平
                ankle_child_local_pos = ankle_horizonal_pos

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

        if self.options.leg_error_tolerance > 0:
            logger.info("足ＩＫブレ固定　【%s足ＩＫ】", direction, decoration=MLogger.DECORATION_LINE)

            prev_sep_fno = 0
            for prev_fno, next_fno in zip(fnos[:-3], fnos[3:]):
                # つま先IK末端の位置
                toe_ik_3ds = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, prev_fno)
                prev_toe_pos = toe_ik_3ds[toe_ik_bone_name]

                # 足IKの位置
                sole_ik_3ds = MServiceUtils.calc_global_pos(model, ik_links, motion, prev_fno)
                prev_sole_pos = sole_ik_3ds[leg_ik_bone_name]

                toe_poses = []
                sole_poses = []
                for fno in range(prev_fno + 1, next_fno + 1):
                    # つま先IK末端の位置(Yはボーンの高さまで無視)
                    toe_ik_3ds = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, fno)
                    toe_poses.append(np.array([toe_ik_3ds[toe_ik_bone_name].x(), max(model.bones[toe_ik_bone_name].position.y(), toe_ik_3ds[toe_ik_bone_name].y()), toe_ik_3ds[toe_ik_bone_name].z()]))

                    # 足IKの位置(Yはボーンの高さまで無視)
                    sole_ik_3ds = MServiceUtils.calc_global_pos(model, ik_links, motion, fno)
                    sole_poses.append(np.array([sole_ik_3ds[leg_ik_bone_name].x(), max(model.bones[leg_ik_bone_name].position.y(), sole_ik_3ds[leg_ik_bone_name].y()), sole_ik_3ds[leg_ik_bone_name].z()]))
                
                # つま先IKの二点間距離
                toe_distances = np.linalg.norm(np.array(toe_poses) - prev_toe_pos.data(), ord=2, axis=1)
                
                # 足IKの二点間距離
                sole_distances = np.linalg.norm(np.array(sole_poses) - prev_sole_pos.data(), ord=2, axis=1)

                if np.max(sole_distances) <= self.options.leg_error_tolerance and prev_sole_pos.y() < 0.5 + model.bones[leg_ik_bone_name].position.y():
                    logger.debug("%s足固定(%s-%s): sole: %s", direction, prev_fno, next_fno, sole_distances)

                    # 足IKがブレの許容範囲内である場合、固定
                    prev_bf = motion.calc_bf(leg_ik_bone_name, prev_fno)

                    # 接地
                    prev_bf.position.setY(0)
                    motion.regist_bf(prev_bf, leg_ik_bone_name, prev_fno)

                    # つま先IKのグローバル位置を再計算
                    toe_ik_3ds = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, prev_fno)
                    toe_ik_global_pos = toe_ik_3ds[toe_ik_bone_name]

                    for fno in range(prev_fno + 1, next_fno + 1):
                        bf = motion.calc_bf(leg_ik_bone_name, fno)
                        bf.position = prev_bf.position.copy()
                        motion.regist_bf(bf, leg_ik_bone_name, fno)

                    for fno in range(prev_fno, next_fno + 1):
                        # つま先IKのグローバル位置を再計算
                        toe_ik_3ds = MServiceUtils.calc_global_pos(model, toe_ik_links, motion, fno)
                        toe_ik_global_pos = toe_ik_3ds[toe_ik_bone_name]

                        if toe_ik_global_pos.y() < 0:
                            # 足IKの行列を再計算
                            sole_ik_3ds, sole_mats = MServiceUtils.calc_global_pos(model, ik_links, motion, fno, return_matrix=True)

                            toe_ik_local_prev_pos = sole_mats[leg_ik_bone_name].inverted() * toe_ik_global_pos
                            toe_ik_local_now_pos = sole_mats[leg_ik_bone_name].inverted() * MVector3D(toe_ik_global_pos.x(), model.bones[toe_ik_bone_name].position.y(), toe_ik_global_pos.z())

                            adjust_toe_qq = MQuaternion.rotationTo(toe_ik_local_prev_pos, toe_ik_local_now_pos)
                            logger.debug("%sつま先ゼロ(%s-%s): toe_ik_global_pos: %s, adjust_toe_qq: %s", direction, prev_fno, next_fno, toe_ik_global_pos.to_log(),
                                         adjust_toe_qq.toEulerAngles4MMD().to_log())

                            prev_bf = motion.calc_bf(leg_ik_bone_name, prev_fno)
                            bf = motion.calc_bf(leg_ik_bone_name, fno)
                            bf.rotation *= adjust_toe_qq

                            if fno > prev_fno and MQuaternion.dotProduct(prev_bf.rotation, bf.rotation) > 0.95:
                                logger.debug("%sつま先回転コピー(%s-%s): toe_ik_global_pos: %s, prev: %s, now: %s", direction, prev_fno, next_fno, toe_ik_global_pos.to_log(),
                                             prev_bf.rotation.toEulerAngles4MMD().to_log(), bf.rotation.toEulerAngles4MMD().to_log())
                                bf.rotation = prev_bf.rotation.copy()
                                
                            motion.regist_bf(bf, leg_ik_bone_name, fno)

                elif np.max(toe_distances) <= self.options.leg_error_tolerance and prev_sole_pos.y() < 0.5 + model.bones[leg_ik_bone_name].position.y():
                    logger.debug("%sつま先固定(%s-%s): sole: %s", direction, prev_fno, next_fno, toe_distances)

                    # つま先位置がブレの許容範囲内である場合、つま先を固定する位置に足IKを置く
                    prev_bf = motion.calc_bf(leg_ik_bone_name, prev_fno)

                    for fidx, fno in enumerate(range(prev_fno + 1, next_fno + 1)):
                        # つま先のグローバル位置
                        toe_pos = MVector3D(toe_poses[fidx])

                        bf = motion.calc_bf(leg_ik_bone_name, fno)
                        bf.position = prev_bf.position.copy() - (toe_pos - prev_toe_pos)
                        motion.regist_bf(bf, leg_ik_bone_name, fno)
                else:
                    logger.debug("×%s固定なし(%s-%s): prev: %s, sole: %s, toe: %s", direction, prev_fno, next_fno, prev_sole_pos.to_log(), sole_distances, toe_distances)

                if prev_fno // 500 > prev_sep_fno:
                    logger.count(f"【{direction}足ＩＫブレ固定】", prev_fno, fnos)
                    prev_sep_fno = prev_fno // 500

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
