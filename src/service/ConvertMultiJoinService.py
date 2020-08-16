# -*- coding: utf-8 -*-
#
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MMultiJoinOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertMultiJoinService():
    def __init__(self, options: MMultiJoinOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "多段統合処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa

            selections = ["{0} ← 回転X: {1}, 回転Y: {2}, 回転Z: {3}, 移動X: {4}, 移動Y: {5}, 移動Z: {6}" \
                          .format(bset[0], bset[1], bset[2], bset[3], bset[4], bset[5], bset[6]) for bset in self.options.target_bones]
            service_data_txt = "{service_data_txt}　対象ボーン: {target_bones}\n".format(service_data_txt=service_data_txt,
                                    target_bones='\n'.join(selections)) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            futures = []

            with ThreadPoolExecutor(thread_name_prefix="join", max_workers=min(5, self.options.max_workers)) as executor:
                for (bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn) in self.options.target_bones:
                    futures.append(executor.submit(self.convert_multi_join, bone_name, rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn))

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
            logger.error("多段統合処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("多段統合処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 多段統合処理実行
    def convert_multi_join(self, bone_name: str, rrxbn: str, rrybn: str, rrzbn: str, rmxbn: str, rmybn: str, rmzbn: str):
        logger.info("多段統合【%s】", bone_name, decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        # 事前に全打ち
        fnos = motion.get_differ_fnos(0, [rrxbn, rrybn, rrzbn, rmxbn, rmybn, rmzbn], limit_degrees=5, limit_length=0.1)

        prev_sep_fno = 0
        for fno in fnos:
            bf = motion.calc_bf(bone_name, fno)
            motion.regist_bf(bf, bone_name, fno)

            if model.bones[bone_name].getRotatable():
                rx_bf = motion.calc_bf(rrxbn, fno)
                motion.regist_bf(rx_bf, rx_bf.name, fno)

                ry_bf = motion.calc_bf(rrybn, fno)
                motion.regist_bf(ry_bf, ry_bf.name, fno)
                
                rz_bf = motion.calc_bf(rrzbn, fno)
                motion.regist_bf(rz_bf, rz_bf.name, fno)
                
            if model.bones[bone_name].getTranslatable():
                mx_bf = motion.calc_bf(rmxbn, fno)
                motion.regist_bf(mx_bf, mx_bf.name, fno)

                my_bf = motion.calc_bf(rmybn, fno)
                motion.regist_bf(my_bf, my_bf.name, fno)

                mz_bf = motion.calc_bf(rmzbn, fno)
                motion.regist_bf(mz_bf, mz_bf.name, fno)

            if fno // 1000 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【キーフレ追加 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                prev_sep_fno = fno // 1000

        logger.info("-- 準備完了【%s】", bone_name)

        prev_sep_fno = 0
        for fno in fnos:
            bf = motion.calc_bf(bone_name, fno)

            if model.bones[bone_name].getRotatable():
                rx_bf = motion.calc_bf(rrxbn, fno) if len(rrxbn) > 0 else VmdBoneFrame(fno)
                ry_bf = motion.calc_bf(rrybn, fno) if len(rrybn) > 0 else VmdBoneFrame(fno)
                rz_bf = motion.calc_bf(rrzbn, fno) if len(rrzbn) > 0 else VmdBoneFrame(fno)
                bf.rotation = ry_bf.rotation * rx_bf.rotation * rz_bf.rotation

                mx_bf = motion.calc_bf(rmxbn, fno) if len(rmxbn) > 0 else VmdBoneFrame(fno)
                my_bf = motion.calc_bf(rmybn, fno) if len(rmybn) > 0 else VmdBoneFrame(fno)
                mz_bf = motion.calc_bf(rmzbn, fno) if len(rmzbn) > 0 else VmdBoneFrame(fno)
                bf.position = my_bf.position + mx_bf.position + mz_bf.position

                motion.regist_bf(bf, bone_name, fno)

            if fno // 1000 > prev_sep_fno and fnos[-1] > 0:
                logger.info("-- %sフレーム目:終了(%s％)【多段統合 - %s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                prev_sep_fno = fno // 1000

        logger.info("-- 統合完了【%s】", bone_name)

        # 元のボーン削除
        if len(rrxbn) > 0 and rrxbn in motion.bones:
            del motion.bones[rrxbn]
        if len(rrybn) > 0 and rrybn in motion.bones:
            del motion.bones[rrybn]
        if len(rrzbn) > 0 and rrzbn in motion.bones:
            del motion.bones[rrzbn]
        if len(rmxbn) > 0 and rmxbn in motion.bones:
            del motion.bones[rmxbn]
        if len(rmybn) > 0 and rmybn in motion.bones:
            del motion.bones[rmybn]
        if len(rmzbn) > 0 and rmzbn in motion.bones:
            del motion.bones[rmzbn]

        # 不要キー削除
        self.options.motion.remove_unnecessary_bf(0, bone_name, self.options.model.bones[bone_name].getRotatable(), \
                                                  self.options.model.bones[bone_name].getTranslatable())
        
        return True

