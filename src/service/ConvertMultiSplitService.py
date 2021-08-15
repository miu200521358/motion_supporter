# -*- coding: utf-8 -*-
#
import logging
import os
import traceback
import numpy as np
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MMultiSplitOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertMultiSplitService():
    def __init__(self, options: MMultiSplitOptions):
        self.options = options
        # 分散前のを保持
        self.prev_motion = options.motion.copy()

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "多段分割処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            selections = ["{0} → 回転(X): {1}, 回転(Y): {2}, 回転(Z): {3}, 移動(X): {4}, 移動(Y): {5}, 移動(Z): {6}" \
                          .format(bset[0], bset[1], bset[2], bset[3], bset[4], bset[5], bset[6]) for bset in self.options.target_bones]
            service_data_txt = "{service_data_txt}　対象ボーン: {target_bones}\n".format(service_data_txt=service_data_txt,
                                    target_bones='\n'.join(selections)) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            motion = self.options.motion
            model = self.options.model

            futures = []

            with ThreadPoolExecutor(thread_name_prefix="split", max_workers=self.options.max_workers) as executor:
                center_mx = ""
                center_my = ""
                center_mz = ""
                for (bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn) in self.options.target_bones:
                    if bone_name not in model.bones or bone_name not in motion.bones:
                        continue
                    
                    if bone_name == "センター":
                        center_mx = rmxbn
                        center_my = rmybn
                        center_mz = rmzbn
                    
                    if bone_name == "グルーブ":
                        futures.append(executor.submit(self.convert_multi_split, bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn, center_mx, center_my, center_mz))
                    else:
                        futures.append(executor.submit(self.convert_multi_split, bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn, "", "", ""))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False
                    
            if self.options.remove_unnecessary_flg:
                # 不要キー削除
                futures = []
                with ThreadPoolExecutor(thread_name_prefix="remove", max_workers=self.options.max_workers) as executor:
                    for (bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn) in self.options.target_bones:
                        if model.bones[bone_name].getRotatable():
                            if len(rrxbn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rrxbn))
                            if len(rrybn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rrybn))
                            if len(rrzbn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rrzbn))

                        if model.bones[bone_name].getTranslatable():
                            if len(rmxbn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rmxbn))
                            if len(rmybn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rmybn))
                            if len(rmzbn) > 0:
                                futures.append(executor.submit(self.remove_unnecessary_bf, rmzbn))

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
            logger.error("多段分割処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("多段分割処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 多段分割処理実行
    def convert_multi_split(self, bone_name: str, rrxbn: str, rrybn: str, rrzbn: str, rmxbn: str, rmybn: str, rmzbn: str, center_mx: str, center_my: str, center_mz: str):
        logger.info("多段分割【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        # 事前に変化量全打ち
        if bone_name == "センター" or bone_name == "グルーブ":
            fnos = self.prev_motion.get_differ_fnos(0, ["センター", "グルーブ"], limit_degrees=70, limit_length=1)
        else:
            fnos = self.prev_motion.get_differ_fnos(0, [bone_name], limit_degrees=70, limit_length=1)

        if len(fnos) == 0:
            return

        prev_sep_fno = 0
        for fno in fnos:
            # 一度そのままキーを登録
            motion.regist_bf(motion.calc_bf(bone_name, fno), bone_name, fno)
            # 補間曲線のため、もう一度取得しなおし
            bf = motion.calc_bf(bone_name, fno)

            if model.bones[bone_name].getRotatable():
                rx_bf = motion.calc_bf(rrxbn, fno)
                motion.copy_interpolation(bf, rx_bf, MBezierUtils.BZ_TYPE_R)
                motion.regist_bf(rx_bf, rx_bf.name, fno, copy_interpolation=True)

                ry_bf = motion.calc_bf(rrybn, fno)
                motion.copy_interpolation(bf, ry_bf, MBezierUtils.BZ_TYPE_R)
                motion.regist_bf(ry_bf, ry_bf.name, fno, copy_interpolation=True)
                
                rz_bf = motion.calc_bf(rrzbn, fno)
                motion.copy_interpolation(bf, rz_bf, MBezierUtils.BZ_TYPE_R)
                motion.regist_bf(rz_bf, rz_bf.name, fno, copy_interpolation=True)

            if model.bones[bone_name].getTranslatable():
                mx_bf = motion.calc_bf(rmxbn, fno)
                motion.copy_interpolation(bf, mx_bf, MBezierUtils.BZ_TYPE_MX)
                motion.regist_bf(mx_bf, mx_bf.name, fno, copy_interpolation=True)

                my_bf = motion.calc_bf(rmybn, fno)
                motion.copy_interpolation(bf, my_bf, MBezierUtils.BZ_TYPE_MY)
                motion.regist_bf(my_bf, my_bf.name, fno, copy_interpolation=True)

                mz_bf = motion.calc_bf(rmzbn, fno)
                motion.copy_interpolation(bf, mz_bf, MBezierUtils.BZ_TYPE_MZ)
                motion.regist_bf(mz_bf, mz_bf.name, fno, copy_interpolation=True)
                
            if fno // 500 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【キーフレ追加 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                prev_sep_fno = fno // 500

        logger.info("分割準備完了【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

        # ローカルX軸
        local_x_axis = model.bones[bone_name].local_x_vector
        if local_x_axis == MVector3D(1, 0, 0) or local_x_axis == MVector3D():
            # 指定が無い場合、腕系はローカルX軸、それ以外はノーマル
            if "腕" in bone_name or "ひじ" in bone_name or "手首" in bone_name:
                local_x_axis = model.get_local_x_axis(bone_name)
            else:
                local_x_axis = None
        logger.debug(f"{bone_name}, local_x_axis: {local_x_axis}")

        prev_sep_fno = 0
        for fno in fnos:
            bf = motion.calc_bf(bone_name, fno)

            # 多段分割
            self.split_bf(fno, bf, local_x_axis, bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn)
            
            if fno // 500 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【多段分割 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                prev_sep_fno = fno // 500
        
        check_fnos = []
        check_prev_next_fnos = {}

        # 分離後に乖離起こしてないかチェック
        for fno_idx, (prev_fno, next_fno) in enumerate(zip(fnos[:-1], fnos[1:])):
            fno = int(prev_fno + ((next_fno - prev_fno) / 2))
            if fno not in fnos:
                check_fnos.append(fno)
                check_prev_next_fnos[fno] = {"prev": prev_fno, "next": next_fno}
        
        check_fnos = list(sorted(list(set(check_fnos))))
        logger.debug("bone_name: %s, check_fnos: %s", bone_name, check_fnos)

        prev_sep_fno = 0
        for fno in check_fnos:
            is_subdiv = False
            prev_motion_bf = self.prev_motion.calc_bf(bone_name, fno).copy()

            if model.bones[bone_name].getRotatable():
                # 回転を分ける
                if local_x_axis:
                    # ローカルX軸がある場合
                    x_qq, y_qq, z_qq, _ = MServiceUtils.separate_local_qq(fno, bone_name, prev_motion_bf.rotation, local_x_axis)
                else:
                    # ローカルX軸の指定が無い場合、グローバルで分ける
                    euler = prev_motion_bf.rotation.toEulerAngles()
                    x_qq = MQuaternion.fromEulerAngles(euler.x(), 0, 0)
                    y_qq = MQuaternion.fromEulerAngles(0, euler.y(), 0)
                    z_qq = MQuaternion.fromEulerAngles(0, 0, euler.z())

                if len(rrxbn) > 0:
                    rx_bf = motion.calc_bf(rrxbn, fno)
                    dot = MQuaternion.dotProduct(x_qq.normalized(), rx_bf.rotation.normalized())
                    if dot < 0.98:
                        is_subdiv = True

                if len(rrybn) > 0:
                    ry_bf = motion.calc_bf(rrybn, fno)
                    dot = MQuaternion.dotProduct(y_qq.normalized(), ry_bf.rotation.normalized())
                    if dot < 0.98:
                        is_subdiv = True

                if len(rrzbn) > 0:
                    rz_bf = motion.calc_bf(rrzbn, fno)
                    dot = MQuaternion.dotProduct(z_qq.normalized(), rz_bf.rotation.normalized())
                    if dot < 0.98:
                        is_subdiv = True

            if model.bones[bone_name].getTranslatable():
                if len(center_mx) > 0 or len(center_my) > 0 or len(center_mz) > 0:
                    # センターとグルーブを両方分割してる場合
                    prev_center_motion_bf = self.prev_motion.calc_bf("センター", fno).copy()
                    if len(center_mx) > 0 and rmxbn == center_mx:
                        prev_motion_bf.position.setX(prev_motion_bf.position.x() + prev_center_motion_bf.position.x())
                    if len(center_my) > 0 and rmybn == center_my:
                        prev_motion_bf.position.setY(prev_motion_bf.position.y() + prev_center_motion_bf.position.y())
                    if len(center_mz) > 0 and rmzbn == center_mz:
                        prev_motion_bf.position.setZ(prev_motion_bf.position.z() + prev_center_motion_bf.position.z())

                # 移動を分ける
                if len(rmxbn) > 0:
                    mx_bf = motion.calc_bf(rmxbn, fno)
                    if np.diff([mx_bf.position.x(), prev_motion_bf.position.x()]) > 0.1:
                        is_subdiv = True

                if len(rmybn) > 0:
                    my_bf = motion.calc_bf(rmybn, fno)
                    if np.diff([my_bf.position.y(), prev_motion_bf.position.y()]) > 0.1:
                        is_subdiv = True

                if len(rmzbn) > 0:
                    mz_bf = motion.calc_bf(rmzbn, fno)
                    if np.diff([mz_bf.position.z(), prev_motion_bf.position.z()]) > 0.1:
                        is_subdiv = True
            
            if is_subdiv:
                # 細分化ONの場合、更に分割する
                if model.bones[bone_name].getRotatable():
                    if len(rrxbn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rrxbn, fno), rrxbn, fno)
                    if len(rrybn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rrybn, fno), rrybn, fno)
                    if len(rrzbn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rrzbn, fno), rrzbn, fno)

                if model.bones[bone_name].getTranslatable():
                    if len(rmxbn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rmxbn, fno), rmxbn, fno)
                    if len(rmybn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rmybn, fno), rmybn, fno)
                    if len(rmzbn) > 0:
                        motion.regist_bf(self.prev_motion.calc_bf(rmzbn, fno), rmzbn, fno)

                # 分割前の値を再登録
                motion.regist_bf(self.prev_motion.calc_bf(bone_name, fno), bone_name, fno)
                subdiv_bf = motion.calc_bf(bone_name, fno)

                if bone_name == "グルーブ" and (len(center_mx) > 0 or len(center_my) > 0 or len(center_mz) > 0):
                    prev_center_motion_bf = self.prev_motion.calc_bf("センター", fno)
                    if len(center_mx) > 0 and rmxbn == center_mx:
                        subdiv_bf.position.setX(subdiv_bf.position.x() + prev_center_motion_bf.position.x())
                    if len(center_my) > 0 and rmybn == center_my:
                        subdiv_bf.position.setY(subdiv_bf.position.y() + prev_center_motion_bf.position.y())
                    if len(center_mz) > 0 and rmzbn == center_mz:
                        subdiv_bf.position.setZ(subdiv_bf.position.z() + prev_center_motion_bf.position.z())

                # 多段分割
                self.split_bf(fno, subdiv_bf, local_x_axis, bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn)

                # prev_fno = check_prev_next_fnos[fno]["prev"]
                # next_fno = check_prev_next_fnos[fno]["next"]

                # logger.info(f"-- 軌跡ズレ防止のため、「{bone_name}」の{prev_fno}F～{next_fno}F間を細分化・不要キー除去します")

                # for f in range(prev_fno, next_fno + 1):

                # # 区間内を初期登録
                # if model.bones[bone_name].getRotatable():
                #     # 回転を分ける
                #     if local_x_axis:
                #         # ローカルX軸がある場合
                #         x_qq, y_qq, z_qq, _ = MServiceUtils.separate_local_qq(f, bone_name, prev_motion_bf.rotation, local_x_axis)
                #     else:
                #         # ローカルX軸の指定が無い場合、グローバルで分ける
                #         euler = prev_motion_bf.rotation.toEulerAngles()
                #         x_qq = MQuaternion.fromEulerAngles(euler.x(), 0, 0)
                #         y_qq = MQuaternion.fromEulerAngles(0, euler.y(), 0)
                #         z_qq = MQuaternion.fromEulerAngles(0, 0, euler.z())

                #     if len(rrxbn) > 0:
                #         prev_rx_bf = self.prev_motion.calc_bf(rrxbn, f).copy()
                #         prev_rx_bf.rotation = x_qq
                #         motion.regist_bf(prev_rx_bf, rrxbn, f)

                #     if len(rrybn) > 0:
                #         prev_ry_bf = self.prev_motion.calc_bf(rrybn, f).copy()
                #         prev_ry_bf.rotation = y_qq
                #         motion.regist_bf(prev_ry_bf, rrybn, f)

                #     if len(rrzbn) > 0:
                #         prev_rz_bf = self.prev_motion.calc_bf(rrzbn, f).copy()
                #         prev_rz_bf.rotation = z_qq
                #         motion.regist_bf(prev_rz_bf, rrzbn, f)

                # if model.bones[bone_name].getTranslatable():
                #     if len(center_mx) > 0 or len(center_my) > 0 or len(center_mz) > 0:
                #         # センターとグルーブを両方分割してる場合
                #         prev_center_motion_bf = self.prev_motion.calc_bf("センター", fno).copy()
                #         if len(center_mx) > 0 and rmxbn == center_mx:
                #             prev_motion_bf.position.setX(prev_motion_bf.position.x() + prev_center_motion_bf.position.x())
                #         if len(center_my) > 0 and rmybn == center_my:
                #             prev_motion_bf.position.setY(prev_motion_bf.position.y() + prev_center_motion_bf.position.y())
                #         if len(center_mz) > 0 and rmzbn == center_mz:
                #             prev_motion_bf.position.setZ(prev_motion_bf.position.z() + prev_center_motion_bf.position.z())

                #     if len(rmxbn) > 0:
                #         prev_mx_bf = self.prev_motion.calc_bf(rmxbn, f).copy()
                #         prev_mx_bf.position.setX(prev_motion_bf.position.x())
                #         motion.regist_bf(prev_mx_bf, rmxbn, f)

                #     if len(rmybn) > 0:
                #         prev_my_bf = self.prev_motion.calc_bf(rmybn, f).copy()
                #         prev_my_bf.position.setY(prev_motion_bf.position.y())
                #         motion.regist_bf(prev_my_bf, rmybn, f)

                #     if len(rmzbn) > 0:
                #         prev_mz_bf = self.prev_motion.calc_bf(rmzbn, f).copy()
                #         prev_mz_bf.position.setZ(prev_motion_bf.position.z())
                #         motion.regist_bf(prev_mz_bf, rmzbn, f)

                # # 不要キー削除
                # futures = []
                # with ThreadPoolExecutor(thread_name_prefix="remove", max_workers=self.options.max_workers) as executor:
                #     if model.bones[bone_name].getRotatable():
                #         if len(rrxbn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rrxbn, start_fno=prev_fno, end_fno=next_fno))
                #         if len(rrybn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rrybn, start_fno=prev_fno, end_fno=next_fno))
                #         if len(rrzbn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rrzbn, start_fno=prev_fno, end_fno=next_fno))

                #     if model.bones[bone_name].getTranslatable():
                #         if len(rmxbn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rmxbn, start_fno=prev_fno, end_fno=next_fno))
                #         if len(rmybn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rmybn, start_fno=prev_fno, end_fno=next_fno))
                #         if len(rmzbn) > 0:
                #             futures.append(executor.submit(self.remove_unnecessary_bf, rmzbn, start_fno=prev_fno, end_fno=next_fno))

                # concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

                # for f in futures:
                #     if not f.result():
                #         return False

            if fno // 1000 > prev_sep_fno and fnos[-1] > 0:
                logger.count(f"【分割後チェック - {bone_name}】", fno, fnos)
                prev_sep_fno = fno // 1000

        logger.info("分割完了【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

        # 元のボーン削除
        if rrxbn != bone_name and rrybn != bone_name and rrzbn != bone_name and rmxbn != bone_name and rmybn != bone_name and rmzbn != bone_name:
            del motion.bones[bone_name]

        # # 跳ねてるの除去
        # futures = []
        # with ThreadPoolExecutor(thread_name_prefix="smooth", max_workers=self.options.max_workers) as executor:
        #     if model.bones[bone_name].getRotatable():
        #         if len(rrxbn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rrxbn))
        #         if len(rrybn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rrybn))
        #         if len(rrzbn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rrzbn))

        #     if model.bones[bone_name].getTranslatable():
        #         if len(rmxbn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rmxbn))
        #         if len(rmybn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rmybn))
        #         if len(rmzbn) > 0:
        #             futures.append(executor.submit(self.smooth_bf, rmzbn))

        # concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        # for f in futures:
        #     if not f.result():
        #         return False

        return True
    
    def split_bf(self, fno: int, bf: VmdBoneFrame, local_x_axis: MVector3D, bone_name: str, rrxbn: str, rrybn: str, rrzbn: str, rmxbn: str, rmybn: str, rmzbn: str):
        motion = self.options.motion
        model = self.options.model

        if model.bones[bone_name].getRotatable():
            # 回転を分ける
            if local_x_axis:
                # ローカルX軸がある場合
                x_qq, y_qq, z_qq, _ = MServiceUtils.separate_local_qq(fno, bone_name, bf.rotation, local_x_axis)
            else:
                # ローカルX軸の指定が無い場合、グローバルで分ける
                euler = bf.rotation.toEulerAngles()
                x_qq = MQuaternion.fromEulerAngles(euler.x(), 0, 0)
                y_qq = MQuaternion.fromEulerAngles(0, euler.y(), 0)
                z_qq = MQuaternion.fromEulerAngles(0, 0, euler.z())
            
            logger.debug(f"fno: {fno}, x_qq: {x_qq.toEulerAngles4MMD().to_log()}, y_qq: {y_qq.toEulerAngles4MMD().to_log()}, z_qq: {z_qq.toEulerAngles4MMD().to_log()}")

            if len(rrybn) > 0 and rrybn != bf.name:
                ry_bf = motion.calc_bf(rrybn, fno)
                ry_bf.rotation *= y_qq
                motion.regist_bf(ry_bf, ry_bf.name, fno)
                # 減算
                bf.rotation *= y_qq.inverted()

            if len(rrxbn) > 0 and rrxbn != bf.name:
                rx_bf = motion.calc_bf(rrxbn, fno)
                rx_bf.rotation *= x_qq
                motion.regist_bf(rx_bf, rx_bf.name, fno)
                # 減算
                bf.rotation *= x_qq.inverted()

            if len(rrzbn) > 0 and rrzbn != bf.name:
                rz_bf = motion.calc_bf(rrzbn, fno)
                rz_bf.rotation *= z_qq
                motion.regist_bf(rz_bf, rz_bf.name, fno)
                # 減算
                bf.rotation *= z_qq.inverted()

            if len(rrxbn) > 0 and rrybn != bf.name and len(rrybn) > 0 and rrxbn != bf.name and len(rrzbn) > 0 and rrzbn != bf.name:
                bf.rotation = MQuaternion()
                motion.regist_bf(bf, bf.name, fno)
        
        if model.bones[bone_name].getTranslatable():
            # 移動を分ける
            if len(rmxbn) > 0 and rmxbn != bf.name:
                mx_bf = motion.calc_bf(rmxbn, fno)
                mx_bf.position.setX(mx_bf.position.x() + bf.position.x())
                motion.regist_bf(mx_bf, mx_bf.name, fno)
                # 減算
                bf.position.setX(0)

            if len(rmybn) > 0 and rmybn != bf.name:
                my_bf = motion.calc_bf(rmybn, fno)
                my_bf.position.setY(my_bf.position.y() + bf.position.y())
                motion.regist_bf(my_bf, my_bf.name, fno)
                # 減算
                bf.position.setY(0)

            if len(rmzbn) > 0 and rmzbn != bf.name:
                mz_bf = motion.calc_bf(rmzbn, fno)
                mz_bf.position.setZ(mz_bf.position.z() + bf.position.z())
                motion.regist_bf(mz_bf, mz_bf.name, fno)
                # 減算
                bf.position.setZ(0)

            if len(rmxbn) > 0 and rmxbn != bf.name and len(rmybn) > 0 and rmybn != bf.name and len(rmzbn) > 0 and rmzbn != bf.name:
                bf.position = MVector3D()
                motion.regist_bf(bf, bf.name, fno)

    def smooth_bf(self, bone_name: str):
        try:
            # 一旦跳ねてるのを除去
            self.options.motion.smooth_bf(0, bone_name, self.options.model.bones[bone_name].getRotatable(), \
                                          self.options.model.bones[bone_name].getTranslatable(), limit_degrees=10)

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("多段分割処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
            return se
        except Exception as e:
            import traceback
            logger.critical("多段分割処理が意図せぬエラーで終了しました。\n\n%s", traceback.print_exc(), decoration=MLogger.DECORATION_BOX)
            raise e

    # 不要キー削除
    def remove_unnecessary_bf(self, bone_name: str, start_fno=-1, end_fno=-1):
        try:
            logger.info("不要キー削除開始【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

            is_show_log = True if start_fno < 0 and end_fno < 0 else False
            self.options.motion.remove_unnecessary_bf(0, bone_name, self.options.model.bones[bone_name].getRotatable(), \
                                                      self.options.model.bones[bone_name].getTranslatable(), start_fno=start_fno, end_fno=end_fno, is_show_log=is_show_log)

            logger.info("不要キー削除完了【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("多段分割処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
            return se
        except Exception as e:
            import traceback
            logger.critical("多段分割処理が意図せぬエラーで終了しました。\n\n%s", traceback.print_exc(), decoration=MLogger.DECORATION_BOX)
            raise e


