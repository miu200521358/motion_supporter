# -*- coding: utf-8 -*-
#
import math
from math import dist
import numpy as np
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MArmIKtoFKOptions, MOptionsDataSet
from mmd.PmxData import PmxModel, Bone # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MParams import BoneLinks # noqa
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException

logger = MLogger(__name__, level=1)


class ConvertArmIKtoFKService():
    def __init__(self, options: MArmIKtoFKOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "腕ＩＫ変換処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_ik2fk()

            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.model, self.options.output_path, False, False, [], None, 0, [])).write()

            logger.info("出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功")

            return result
        except SizingException as se:
            logger.error("腕ＩＫ変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("腕ＩＫ変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 腕ＩＫ変換処理実行
    def convert_ik2fk(self):
        futures = []

        with ThreadPoolExecutor(thread_name_prefix="ik2fk", max_workers=self.options.max_workers) as executor:
            for bone in self.options.model.bones.values():
                if "右腕ＩＫ" == bone.name or "右腕IK" == bone.name or "左腕ＩＫ" == bone.name or "左腕IK" == bone.name:
                    # 腕IK系の場合、処理開始
                    futures.append(executor.submit(self.convert_target_ik2fk, bone))

        concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        for f in futures:
            if not f.result():
                return False

        return True

    # 1つのボーンに対する腕ＩＫ変換処理
    def convert_target_ik2fk(self, ik_bone: Bone):
        motion = self.options.motion
        model = self.options.model
        bone_name = ik_bone.name

        logger.info("-- 腕ＩＫ変換準備:開始【%s】", bone_name)

        # モデルのIKボーンのリンク
        target_links = model.create_link_2_top_one(bone_name, is_defined=False)

        # モデルの人差し指先ボーンのリンク
        finger_bone_name = "{0}人指先実体".format(bone_name[0])
        finger2_bone_name = "{0}小指先実体".format(bone_name[0])
        wrist_bone_name = "{0}手首".format(bone_name[0])
        finger_links = model.create_link_2_top_one(finger_bone_name, is_defined=False)
        finger2_links = model.create_link_2_top_one(finger2_bone_name, is_defined=False)

        # モデルのIKリンク
        if not (ik_bone.ik.target_index in model.bone_indexes and model.bone_indexes[ik_bone.ik.target_index] in model.bones):
            raise SizingException("{0} のTargetが有効なINDEXではありません。PMXの構造を確認してください。".format(bone_name))

        # IKエフェクタ
        effector_bone_name = model.bone_indexes[ik_bone.ik.target_index]
        effector_links = model.create_link_2_top_one(effector_bone_name, is_defined=False)
        ik_links = BoneLinks()

        # 末端にエフェクタ
        effector_bone = model.bones[effector_bone_name].copy()
        effector_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)
        ik_links.append(effector_bone)

        for ik_link in ik_bone.ik.link:
            # IKリンクを末端から順に追加
            if not (ik_link.bone_index in model.bone_indexes and model.bone_indexes[ik_link.bone_index] in model.bones):
                raise SizingException("{0} のLinkに無効なINDEXが含まれています。PMXの構造を確認してください。".format(bone_name))
            
            link_bone = model.bones[model.bone_indexes[ik_link.bone_index]].copy()

            if link_bone.fixed_axis != MVector3D():
                # 捩り系は無視
                continue

            # 単位角
            link_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)

            # # 角度制限
            # if ik_link.limit_angle == 1:
            #     link_bone.limit_min = ik_link.limit_min
            #     link_bone.limit_max = ik_link.limit_max

            ik_links.append(link_bone)

        # 回転移管先ボーン
        transferee_bone = self.get_transferee_bone(ik_bone, effector_bone)

        # 移管先ボーンのローカル軸
        transferee_local_x_axis = model.get_local_x_axis(transferee_bone.name)

        # 差異の大きい箇所にFKキーフレ追加
        fnos = motion.get_differ_fnos(0, [bone_name], limit_degrees=20, limit_length=0.5)

        prev_sep_fno = 0
        for fno in fnos:
            for link_name in list(ik_links.all().keys())[1:]:
                bf = motion.calc_bf(link_name, fno)
                motion.regist_bf(bf, link_name, fno)

            if fno // 500 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【キーフレ追加 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                prev_sep_fno = fno // 500

        logger.info("-- 腕ＩＫ変換準備:終了【%s】", bone_name)

        org_motion = motion.copy()

        # 元モーションを保持したら、IKキーフレ削除
        del motion.bones[bone_name]

        for fno in fnos:
            # グローバル位置計算(元モーションの位置)
            target_ik_global_3ds = MServiceUtils.calc_global_pos(model, target_links, org_motion, fno)
            finger_global_3ds = MServiceUtils.calc_global_pos(model, finger_links, org_motion, fno)
            finger2_global_3ds = MServiceUtils.calc_global_pos(model, finger2_links, org_motion, fno)
            target_effector_pos = target_ik_global_3ds[bone_name]

            prev_diff = MVector3D()

            org_bfs = {}
            for link_name in list(ik_links.all().keys())[1:]:
                # 元モーションの角度で保持
                bf = org_motion.calc_bf(link_name, fno).copy()
                org_bfs[link_name] = bf
                # 今のモーションも前のキーフレをクリアして再セット
                motion.regist_bf(bf, link_name, fno)

            # IK計算実行
            for ik_cnt in range(50):
                MServiceUtils.calc_IK(model, effector_links, motion, fno, target_effector_pos, ik_links, max_count=1)

                # どちらにせよ一旦bf確定
                for link_name in list(ik_links.all().keys())[1:]:
                    ik_bf = motion.calc_bf(link_name, fno)
                    motion.regist_bf(ik_bf, link_name, fno)

                # 現在のエフェクタ位置
                now_global_3ds = MServiceUtils.calc_global_pos(model, effector_links, motion, fno)
                now_effector_pos = now_global_3ds[effector_bone_name]

                # 現在のエフェクタ位置との差分(エフェクタ位置が指定されている場合のみ)
                diff_pos = MVector3D() if target_effector_pos == MVector3D() else target_effector_pos - now_effector_pos

                if prev_diff == MVector3D() or (prev_diff != MVector3D() and diff_pos.length() < prev_diff.length()):
                    if diff_pos.length() < 0.1:
                        logger.debug("☆腕ＩＫ変換成功(%s): f: %s(%s), 指定 [%s], 現在[%s], 差異[%s(%s)]", ik_cnt, fno, bone_name, \
                                     target_effector_pos.to_log(), now_effector_pos.to_log(), diff_pos.to_log(), diff_pos.length())

                        # org_bfを保持し直し
                        for link_name in list(ik_links.all().keys())[1:]:
                            bf = motion.calc_bf(link_name, fno).copy()
                            org_bfs[link_name] = bf
                            logger.test("org_bf保持: %s [%s]", link_name, bf.rotation.toEulerAngles().to_log())

                        # そのまま終了
                        break
                    elif prev_diff == MVector3D() or diff_pos.length() < prev_diff.length():
                        logger.debug("☆腕ＩＫ変換ちょっと失敗採用(%s): f: %s(%s), 指定 [%s], 現在[%s], 差異[%s(%s)]", ik_cnt, fno, bone_name, \
                                     target_effector_pos.to_log(), now_effector_pos.to_log(), diff_pos.to_log(), diff_pos.length())

                        # org_bfを保持し直し
                        for link_name in list(ik_links.all().keys())[1:]:
                            bf = motion.calc_bf(link_name, fno).copy()
                            org_bfs[link_name] = bf
                            logger.test("org_bf保持: %s [%s]", link_name, bf.rotation.toEulerAngles().to_log())

                        # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                        if prev_diff == diff_pos or np.count_nonzero(np.where(np.abs(diff_pos.data()) > 0.05, 1, 0)) == 0:
                            logger.debug("動きがないので終了")
                            break

                        # 前回差異を保持
                        prev_diff = diff_pos
                    else:
                        logger.debug("★腕ＩＫ変換ちょっと失敗不採用(%s): f: %s(%s), 指定 [%s], 現在[%s], 差異[%s(%s)]", ik_cnt, fno, bone_name, \
                                     target_effector_pos.to_log(), now_effector_pos.to_log(), diff_pos.to_log(), diff_pos.length())

                        # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                        if prev_diff == diff_pos or np.count_nonzero(np.where(np.abs(diff_pos.data()) > 0.05, 1, 0)) == 0:
                            break
                else:
                    logger.debug("★腕ＩＫ変換失敗(%s): f: %s(%s), 指定 [%s], 現在[%s], 差異[%s(%s)]", ik_cnt, fno, bone_name, \
                                 target_effector_pos.to_log(), now_effector_pos.to_log(), diff_pos.to_log(), diff_pos.length())

                    # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                    if prev_diff == diff_pos or np.count_nonzero(np.where(np.abs(diff_pos.data()) > 0.05, 1, 0)) == 0:
                        logger.debug("動きがないので終了")
                        break
            
            # 最後に成功したところに戻す
            for link_name in list(ik_links.all().keys())[1:]:
                bf = org_bfs[link_name].copy()
                logger.debug("確定bf: %s [%s]", link_name, bf.rotation.toEulerAngles().to_log())
                motion.regist_bf(bf, link_name, fno)
            
            # 指先の現在の位置を再計算
            if finger_links and finger_links.get(finger_bone_name) and finger_links.get(wrist_bone_name) and \
                    finger2_links and finger2_links.get(finger2_bone_name) and finger2_links.get(wrist_bone_name) and transferee_bone.name == wrist_bone_name:
                # 手首がある場合のみ、再計算
                now_finger_global_3ds, now_finger_matrixs = MServiceUtils.calc_global_pos(model, finger_links, motion, fno, return_matrix=True)
                # 人指先のローカル位置
                finger_initial_local_pos = now_finger_matrixs[wrist_bone_name].inverted() * now_finger_global_3ds[finger_bone_name]
                finger_local_pos = now_finger_matrixs[wrist_bone_name].inverted() * finger_global_3ds[finger_bone_name]
                finger_rotation = MQuaternion.rotationTo(finger_initial_local_pos, finger_local_pos)
                logger.debug("finger_rotation: %s [%s]", finger_bone_name, finger_rotation.toEulerAngles().to_log())

                finger_x_qq, finger_y_qq, finger_z_qq, _ = MServiceUtils.separate_local_qq(fno, bone_name, finger_rotation, transferee_local_x_axis)
                logger.debug("finger_x_qq: %s [%s]", finger_bone_name, finger_x_qq.toEulerAngles().to_log())
                logger.debug("finger_y_qq: %s [%s]", finger_bone_name, finger_y_qq.toEulerAngles().to_log())
                logger.debug("finger_z_qq: %s [%s]", finger_bone_name, finger_z_qq.toEulerAngles().to_log())

                # 手首の回転は、手首から見た指先の方向
                transferee_bf = motion.calc_bf(transferee_bone.name, fno)
                transferee_bf.rotation = finger_rotation

                # 捩りなしの状態で一旦登録する
                motion.regist_bf(transferee_bf, transferee_bone.name, fno)

                now_finger2_global_3ds, now_finger2_matrixs = MServiceUtils.calc_global_pos(model, finger2_links, motion, fno, return_matrix=True)
                # 小指先のローカル位置
                finger2_initial_local_pos = now_finger2_matrixs[wrist_bone_name].inverted() * now_finger2_global_3ds[finger2_bone_name]
                finger2_local_pos = now_finger2_matrixs[wrist_bone_name].inverted() * finger2_global_3ds[finger2_bone_name]
                finger2_rotation = MQuaternion.rotationTo(finger2_initial_local_pos, finger2_local_pos)
                logger.debug("finger2_rotation: %s [%s]", finger2_bone_name, finger2_rotation.toEulerAngles().to_log())
                
                finger2_x_qq = MQuaternion.fromAxisAndAngle(transferee_local_x_axis, finger_x_qq.toDegree() + finger2_rotation.toDegree())
                transferee_bf.rotation = finger_y_qq * finger2_x_qq * finger_z_qq
                motion.regist_bf(transferee_bf, transferee_bone.name, fno)
                logger.debug("transferee_qq: %s [%s], x [%s]", transferee_bone.name, transferee_bf.rotation.toEulerAngles().to_log(), finger2_x_qq.toEulerAngles().to_log())

            logger.info("-- %sフレーム目:終了(%s％)【腕ＩＫ変換 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)

    # IKターゲットの回転量移管先を取得
    # 現在のターゲットが表示されてない場合、子で同じ位置にあるのを採用
    def get_transferee_bone(self, ik_bone: Bone, effector_bone: Bone):
        if effector_bone.getVisibleFlag():
            # エフェクタが表示対象なら、エフェクタ自身
            return effector_bone

        # エフェクタが表示対象外なら、子ボーンの中から、同じ位置のを取得

        # 子ボーンリスト取得
        child_bones = self.options.model.get_child_bones(ik_bone)

        for cbone in child_bones:
            if cbone.position.to_log() == effector_bone.position.to_log():
                return cbone

        # 最後まで取れなければ、とりあえずエフェクタ
        return effector_bone



