# -*- coding: utf-8 -*-
#
import struct
from module.MOptions import MOptionsDataSet
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class VmdWriter():
    def __init__(self, data_set: MOptionsDataSet):
        self.data_set = data_set

    def write(self):
        """Write VMD data to a file"""
        fout = open(self.data_set.output_vmd_path, "wb")

        # header
        fout.write(b'Vocaloid Motion Data 0002\x00\x00\x00\x00\x00')

        bone_frames = self.data_set.motion.get_bone_frames()
        morph_frames = self.data_set.motion.get_morph_frames()
        camera_frames = self.data_set.motion.get_camera_frames()

        if len(bone_frames) > 0 or len(morph_frames) > 0:
            try:
                # モデル名を20byteで切る
                model_bname = self.data_set.rep_model.name.encode('cp932').decode('shift_jis').encode('shift_jis')[:20]
            except Exception:
                logger.warning("モデル名に日本語・英語で判読できない文字が含まれているため、仮モデル名を設定します。 %s", self.data_set.rep_model.name, decoration=MLogger.DECORATION_BOX)
                model_bname = "Vmd Sized Model".encode('shift_jis')[:20]

            # 20文字に満たなかった場合、埋める
            model_bname = model_bname.ljust(20, b'\x00')
                
            fout.write(model_bname)
        else:
            # カメラ・照明
            fout.write(b'\x83J\x83\x81\x83\x89\x81E\x8f\xc6\x96\xbe\x00on Data')
        
        # bone frames
        fout.write(struct.pack('<L', len(bone_frames)))  # ボーンフレーム数
        for bf in bone_frames:
            bf.write(fout)
        fout.write(struct.pack('<L', len(morph_frames)))  # 表情キーフレーム数
        for mf in morph_frames:
            mf.write(fout)
        fout.write(struct.pack('<L', len(camera_frames)))  # カメラキーフレーム数
        for cf in camera_frames:
            cf.write(fout)
        fout.write(struct.pack('<L', len(self.data_set.motion.lights)))  # 照明キーフレーム数
        for cf in self.data_set.motion.lights:
            cf.write(fout)
        fout.write(struct.pack('<L', len(self.data_set.motion.shadows)))  # セルフ影キーフレーム数
        for cf in self.data_set.motion.shadows:
            cf.write(fout)
            
        if len(camera_frames) == 0:
            fout.write(struct.pack('<L', len(self.data_set.motion.showiks)))  # モデル表示・IK on/offキーフレーム数
            for sf in self.data_set.motion.showiks:
                sf.write(fout)
        
        fout.close()
