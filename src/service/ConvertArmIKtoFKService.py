# -*- coding: utf-8 -*-
#
import math
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
from utils.MException import SizingException, MKilledException

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
            service_data_txt = "{service_data_txt}　腕ＩＫありモデル: {ik_model}({ik_model_name})\n".format(service_data_txt=service_data_txt,
                                    ik_model=os.path.basename(self.options.motion.path), ik_model_name=self.options.ik_model.name) # noqa
            service_data_txt = "{service_data_txt}　腕FKモデル: {ik_model}({ik_model_name})\n".format(service_data_txt=service_data_txt,
                                    ik_model=os.path.basename(self.options.motion.path), ik_model_name=self.options.fk_model.name) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_ik2fk()

            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.fk_model, self.options.output_path, False, False, [], None, 0, [])).write()

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
            for bone in self.options.ik_model.bones.values():
                if "右腕ＩＫ" == bone.name or "右腕IK" == bone.name or "左腕ＩＫ" == bone.name or "左腕IK" == bone.name:
                    # 腕IK系の場合、処理開始
                    futures.append(executor.submit(self.convert_target_ik2fk, bone))

        concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        for f in futures:
            if not f.result():
                return False

        if self.options.remove_unnecessary_flg:
            # 不要キー削除処理
            futures = []

            with ThreadPoolExecutor(thread_name_prefix="remove", max_workers=self.options.max_workers) as executor:
                for bone_name in ["右腕", "右ひじ", "右手首", "左腕", "左ひじ", "左手首"]:
                    futures.append(executor.submit(self.remove_unnecessary_bf, bone_name))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False

        return True

    # 1つのボーンに対する腕ＩＫ変換処理
    def convert_target_ik2fk(self, ik_bone: Bone):
        motion = self.options.motion
        ik_model = self.options.ik_model
        fk_model = self.options.fk_model
        bone_name = ik_bone.name

        logger.info("-- 腕ＩＫ変換準備:開始【%s】", bone_name)

        org_motion = motion.copy()

        # モデルのIKボーンのリンク
        target_links = ik_model.create_link_2_top_one(bone_name, is_defined=False)

        arm_bone_name = "{0}腕".format(bone_name[0])

        # モデルの人差し指先ボーンのリンク
        wrist_bone_name = "{0}手首".format(bone_name[0])
        wrist_twist_bone_name = "{0}手捩".format(bone_name[0])

        # モデルのIKリンク
        if not (ik_bone.ik.target_index in ik_model.bone_indexes and ik_model.bone_indexes[ik_bone.ik.target_index] in ik_model.bones):
            raise SizingException("{0} のTargetが有効なINDEXではありません。PMXの構造を確認してください。".format(bone_name))

        # IKエフェクタ
        effector_bone_name = ik_model.bone_indexes[ik_bone.ik.target_index]
        effector_links = ik_model.create_link_2_top_one(effector_bone_name, is_defined=False)
        ik_links = BoneLinks()

        # 末端にエフェクタ
        effector_bone = ik_model.bones[effector_bone_name].copy()
        effector_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)
        ik_links.append(effector_bone)

        target_bones = [bone_name]
        twist_bones = []

        # 回転移管先ボーン(手首)
        transferee_bone = self.get_transferee_bone(ik_bone, effector_bone)
        # 移管先までのリンク
        transferee_links = ik_model.create_link_2_top_one(transferee_bone.name, is_defined=False)

        for ik_link in ik_bone.ik.link:
            # IKリンクを末端から順に追加
            if not (ik_link.bone_index in ik_model.bone_indexes and ik_model.bone_indexes[ik_link.bone_index] in ik_model.bones):
                raise SizingException("{0} のLinkに無効なINDEXが含まれています。PMXの構造を確認してください。".format(bone_name))
            
            link_bone = ik_model.bones[ik_model.bone_indexes[ik_link.bone_index]].copy()

            if link_bone.fixed_axis != MVector3D():
                # 捩り系として保持
                twist_bones.append(link_bone.name)
                # 捩り系は無視
                continue

            # 単位角
            link_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)

            # # 角度制限
            # if ik_link.limit_angle == 1:
            #     link_bone.limit_min = ik_link.limit_min
            #     link_bone.limit_max = ik_link.limit_max

            ik_links.append(link_bone)
            target_bones.append(link_bone.name)

        # 精度優先で全打ち
        fnos = motion.get_bone_fnos(*(list(ik_links.all().keys()) + target_bones + twist_bones))
        fnos = [f for f in range(fnos[-1] + 1)]

        prev_sep_fno = 0
        for fno in fnos:
            for link_name in list(ik_links.all().keys())[1:]:
                bf = motion.calc_bf(link_name, fno)

                if link_name == arm_bone_name:
                    for twist_bone in twist_bones:
                        # 腕は腕捩りの結果を加算する
                        twist_bf = motion.calc_bf(twist_bone, fno)
                        bf.rotation = bf.rotation * twist_bf.rotation

                        # 捩りボーンをクリアする
                        twist_bf.rotation = MQuaternion()
                        motion.regist_bf(twist_bf, twist_bone, fno)

                motion.regist_bf(bf, link_name, fno)

            # 手捩りボーンを手首に乗せる
            if wrist_twist_bone_name in motion.bones:
                wrist_twist_bf = motion.calc_bf(wrist_twist_bone_name, fno)
                wrist_bf = motion.calc_bf(wrist_bone_name, fno)
                wrist_bf.rotation = wrist_twist_bf.rotation * wrist_bf.rotation

                motion.regist_bf(wrist_bf, wrist_bf.name, fno)

                wrist_twist_bf.rotation = MQuaternion()
                motion.regist_bf(wrist_twist_bf, wrist_twist_bf.name, fno)

            # 腕IKも設定
            bf = motion.calc_bf(bone_name, fno)
            motion.regist_bf(bf, bone_name, fno)

            if fno // 500 > prev_sep_fno and fnos[-1] > 0:
                logger.count(f"【キーフレ追加 - {bone_name}】", fno, fnos)
                prev_sep_fno = fno // 500

        logger.info("-- 腕ＩＫ変換準備:終了【%s】", bone_name)

        fk_motion = motion.copy()

        # IKボーンを削除
        if bone_name in motion.bones:
            del motion.bones[bone_name]

        # if bone_name in fk_motion.bones:
        #     del fk_motion.bones[bone_name]

        # 捩りボーンを削除
        for twist_bone in twist_bones:
            if twist_bone in fk_motion.bones:
                del fk_motion.bones[twist_bone]

            if twist_bone in motion.bones:
                del motion.bones[twist_bone]

        if wrist_twist_bone_name in fk_motion.bones:
            del fk_motion.bones[wrist_twist_bone_name]

        if wrist_twist_bone_name in motion.bones:
            del motion.bones[wrist_twist_bone_name]

        prev_sep_fno = 0
        for fidx, fno in enumerate(fnos):
            # グローバル位置計算(元モーションの位置)
            target_ik_global_3ds = MServiceUtils.calc_global_pos(ik_model, target_links, org_motion, fno)
            target_effector_pos = target_ik_global_3ds[bone_name]

            # IK計算実行
            MServiceUtils.calc_IK(ik_model, effector_links, fk_motion, fno, target_effector_pos, ik_links, max_count=10)

            # 現在のエフェクタ位置
            now_global_3ds = MServiceUtils.calc_global_pos(ik_model, transferee_links, fk_motion, fno)
            now_effector_pos = now_global_3ds[transferee_bone.name]
            logger.debug("(%s) target_effector_pos: %s [%s] ------------------", fno, bone_name, target_effector_pos.to_log())
            logger.debug("(%s) now_effector_pos: %s [%s]", fno, bone_name, now_effector_pos.to_log())

            for link_name in list(ik_links.all().keys())[1:]:
                fk_bf = fk_motion.calc_bf(link_name, fno)
                logger.debug("確定bf(%s): %s [%s]", fno, link_name, fk_bf.rotation.toEulerAngles4MMD().to_log())

                # 確定した角度をそのまま登録
                bf = motion.calc_bf(link_name, fno)
                bf.rotation = fk_bf.rotation.copy()
                motion.regist_bf(bf, link_name, fno)

            if fno // 500 > prev_sep_fno:
                logger.count("【腕ＩＫ変換 - {0}】".format(bone_name), fno, fnos)
                prev_sep_fno = fno // 500

        # 終わったら手首FK再計算
        self.recalc_wrist_fk(ik_bone, target_links, effector_links, fnos, org_motion, effector_bone)

        return True

    # IKターゲットの回転量移管先を取得
    # 現在のターゲットが表示されてない場合、子で同じ位置にあるのを採用
    def get_transferee_bone(self, ik_bone: Bone, effector_bone: Bone):
        if effector_bone.getVisibleFlag():
            # エフェクタが表示対象なら、エフェクタ自身
            return effector_bone

        # エフェクタが表示対象外なら、子ボーンの中から、同じ位置のを取得

        # 子ボーンリスト取得
        child_bones = self.options.ik_model.get_child_bones(ik_bone)

        for cbone in child_bones:
            if cbone.position.to_log() == effector_bone.position.to_log():
                return cbone

        # 最後まで取れなければ、とりあえずエフェクタ
        return effector_bone

    # 手首FK再計算
    def recalc_wrist_fk(self, ik_bone: Bone, target_links: BoneLinks, effector_links: BoneLinks, fnos: int, org_motion: VmdMotion, effector_bone: Bone):
        motion = self.options.motion
        ik_model = self.options.ik_model
        fk_model = self.options.fk_model
        bone_name = ik_bone.name

        logger.info("-- 手首再調整:開始【%s】", bone_name)

        # 回転移管先ボーン(手首)
        transferee_bone = self.get_transferee_bone(ik_bone, effector_bone)
        # 移管先までのリンク
        transferee_links = fk_model.create_link_2_top_one(transferee_bone.name, is_defined=False)
        # 回転移管先のローカルX軸
        transferee_local_x_axis = fk_model.get_local_x_axis(transferee_bone.name)
        # 手首先の初期グローバル位置
        _, initial_effector_matrixs = MServiceUtils.calc_global_pos(fk_model, transferee_links, VmdMotion(), 0, return_matrix=True)
        initial_effector_global_pos = initial_effector_matrixs[transferee_bone.name] * transferee_local_x_axis

        # FK手首先ボーンを手動生成（ローカルXを伸ばしただけ）
        wrist_fk_tail_bone = Bone(f"{bone_name[0]}手首先実体FK", "", initial_effector_global_pos, -1, 0, 0)
        # 移管先に親を付ける
        wrist_fk_tail_bone.index = len(fk_model.bones.keys())
        wrist_fk_tail_bone.parent_index = fk_model.bones[transferee_bone.name].index
        fk_model.bones[wrist_fk_tail_bone.name] = wrist_fk_tail_bone
        fk_model.bone_indexes[wrist_fk_tail_bone.index] = wrist_fk_tail_bone.name
        # 移管先までのリンクを撮り直す
        wrist_tail_fk_links = fk_model.create_link_2_top_one(wrist_fk_tail_bone.name, is_defined=False)

        # IK手首先ボーンを手動生成（ローカルXを伸ばしただけ）
        wrist_ik_tail_bone = Bone(f"{bone_name[0]}手首先実体IK", "", initial_effector_global_pos, -1, 0, 0)
        # 移管先に親を付ける
        wrist_ik_tail_bone.index = len(ik_model.bones.keys())
        wrist_ik_tail_bone.parent_index = ik_model.bones[transferee_bone.name].index
        ik_model.bones[wrist_ik_tail_bone.name] = wrist_ik_tail_bone
        ik_model.bone_indexes[wrist_ik_tail_bone.index] = wrist_ik_tail_bone.name
        # IKの先にも延ばす
        wrist_tail_ik_links = ik_model.create_link_2_top_one(wrist_ik_tail_bone.name, is_defined=False)
        
        prev_sep_fno = 0
        for fno_idx, fno in enumerate(fnos):
            logger.debug(f"f: {fno}, {bone_name} ---------------------")

            # 元モデルデータ --------

            # 元モーションの手首先のグローバル座標と行列
            org_target_global_3ds = MServiceUtils.calc_global_pos(ik_model, wrist_tail_ik_links, org_motion, fno)
            # 手首先のグローバル位置
            org_target_global_wrist_tail_pos = org_target_global_3ds[wrist_ik_tail_bone.name]

            # 手首先までのグローバル座標と行列(腕IKは無視)
            org_initial_global_3ds, org_initial_matrixs = MServiceUtils.calc_global_pos(fk_model, wrist_tail_fk_links, motion, fno, return_matrix=True)
            # 手首先の初期グローバル位置を求める
            org_initial_global_wrist_tail_pos = org_initial_global_3ds[wrist_fk_tail_bone.name]
            # 手首までの行列
            org_initial_wrist_matrix = org_initial_matrixs[transferee_bone.name].copy()
            # 手首の回転

            # 腕IKからみた初期手首先ローカル位置
            initial_local_arm_ik_pos = org_initial_wrist_matrix.inverted() * org_initial_global_wrist_tail_pos
            # 腕IKからみた目標手首先ローカル位置
            target_local_arm_ik_pos = org_initial_wrist_matrix.inverted() * org_target_global_wrist_tail_pos

            transferee_qq = MQuaternion.rotationTo(initial_local_arm_ik_pos.normalized(), target_local_arm_ik_pos.normalized())
            transferee_qq.normalize()

            logger.debug(f"org_initial_global_wrist_tail_pos: {org_initial_global_wrist_tail_pos.to_log()}")
            logger.debug(f"org_target_global_wrist_tail_pos: {org_target_global_wrist_tail_pos.to_log()}")
            logger.debug(f"initial_local_arm_ik_pos: {initial_local_arm_ik_pos.to_log()}")
            logger.debug(f"target_local_arm_ik_pos: {target_local_arm_ik_pos.to_log()}")
            logger.debug(f"transferee_qq.rotation: {transferee_qq.toEulerAngles4MMD().to_log()}")

            # 移管先ボーンの回転に置き換え(変換後モーション)
            transferee_bf = motion.calc_bf(transferee_bone.name, fno)
            transferee_bf.rotation *= transferee_qq

            # 登録
            motion.regist_bf(transferee_bf, transferee_bf.name, fno)
            
            if fno // 500 > prev_sep_fno:
                logger.count("【手首再調整 - {0}】".format(bone_name), fno, fnos)
                prev_sep_fno = fno // 500

        return True


    # 不要キー削除
    def remove_unnecessary_bf(self, bone_name: str):
        try:
            self.options.motion.remove_unnecessary_bf(0, bone_name, self.options.ik_model.bones[bone_name].getRotatable(), \
                                                      self.options.ik_model.bones[bone_name].getTranslatable())

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("腕ＩＫ変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
            return se
        except Exception as e:
            import traceback
            logger.critical("腕ＩＫ変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.print_exc(), decoration=MLogger.DECORATION_BOX)
            raise e

