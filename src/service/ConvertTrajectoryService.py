# -*- coding: utf-8 -*-
#
from math import ceil
import numpy as np
import logging
import os
import traceback
import shutil

from module.MOptions import MTrajectoryOptions
from mmd.PmxData import PmxModel, Bone, Vertex, Bdef1, Material, DisplaySlot
from mmd.PmxWriter import PmxWriter
from module.MParams import BoneLinks
from module.MMath import MVector2D, MVector3D, MVector4D
from utils import MServiceUtils, MFileUtils
from utils.MLogger import MLogger
from utils.MException import SizingException

logger = MLogger(__name__, level=1)


class ConvertTrajectoryService:
    def __init__(self, options: MTrajectoryOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "モーフ条件調整変換処理実行\n------------------------\nexeバージョン: {version_name}\n".format(
                version_name=self.options.version_name
            )
            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(
                service_data_txt=service_data_txt, vmd=os.path.basename(self.options.motion.path)
            )

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result, model = self.create_trajectory()

            # 最後に出力
            if result:
                PmxWriter().write(model, self.options.output_path)
                shutil.copy(
                    MFileUtils.resource_path("src/resources/rainbow.png"),
                    self.options.output_path.replace(os.path.basename(self.options.output_path), "rainbow.png"),
                )

                logger.info(
                    "出力終了: %s",
                    os.path.basename(self.options.output_path),
                    decoration=MLogger.DECORATION_BOX,
                    title="成功",
                )

            return result
        except SizingException as se:
            logger.error("モーフ条件調整変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical(
                "モーフ条件調整変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX
            )
        finally:
            logging.shutdown()

    def create_trajectory(self):
        base_model = PmxModel()
        base_model.bones["全ての親"] = Bone(
            name="全ての親",
            english_name="全ての親",
            position=MVector3D(),
            parent_index=-1,
            layer=0,
            flag=(0x0002 | 0x0004 | 0x0008 | 0x0010),
        )
        base_model.bones["全ての親"].index = 0

        base_model.bones["センター"] = Bone(
            name="センター",
            english_name="センター",
            position=MVector3D(0, 8, 0),
            parent_index=0,
            layer=0,
            flag=(0x0002 | 0x0004 | 0x0008 | 0x0010),
        )
        base_model.bones["センター"].index = 1

        base_model.bones["グルーブ"] = Bone(
            name="グルーブ",
            english_name="グルーブ",
            position=MVector3D(0, 8.2, 0),
            parent_index=1,
            layer=0,
            flag=(0x0002 | 0x0004 | 0x0008 | 0x0010),
        )
        base_model.bones["グルーブ"].index = 1

        # 仮モデルのセンターリンク
        target_links = BoneLinks()
        target_links.append(base_model.bones["全ての親"].copy())
        target_links.append(base_model.bones["センター"].copy())
        target_links.append(base_model.bones["グルーブ"].copy())

        # ------------------

        model = PmxModel()
        model.name = f"軌跡モデル - {os.path.basename(self.options.motion.path)}"
        model.comment = f"元モーション: {os.path.basename(self.options.motion.path)}"
        model.bones["全ての親"] = Bone(
            name="全ての親",
            english_name="全ての親",
            position=MVector3D(),
            parent_index=-1,
            layer=0,
            flag=(0x0002 | 0x0004 | 0x0008 | 0x0010),
            tail_position=MVector3D(0, 0, -5),
        )
        model.bones["全ての親"].index = 0

        # モーフの固定表示枠
        model.display_slots["全ての親"] = DisplaySlot("Root", "Root", 1, 1)
        model.display_slots["全ての親"].references.append((0, 0))
        model.display_slots["表情"] = DisplaySlot("表情", "Exp", 1, 1)

        model.textures.append("")
        model.textures.append("rainbow.png")

        WIDTH = 0.1
        NORMAL_VEC = MVector3D(0, 1, 0)
        ROOT_BDEF1 = Bdef1(0)

        motion = self.options.motion
        fnos = sorted(list(motion.bones["センター"].keys()))

        mat_name = "軌跡"
        model.materials[mat_name] = Material(
            name=mat_name,
            english_name=mat_name,
            diffuse_color=MVector3D(1, 1, 1),
            alpha=1,
            specular_factor=0,
            specular_color=MVector3D(0, 0, 0),
            ambient_color=MVector3D(0.5, 0.5, 0.5),
            flag=(0x01),
            edge_color=MVector4D(0, 0, 0, 0),
            edge_size=0,
            texture_index=1,
            sphere_texture_index=-1,
            sphere_mode=0,
            toon_sharing_flag=0,
            toon_texture_index=0,
        )

        # 色をフレーム数分用意する
        uvs = np.linspace(0, 1, num=(fnos[-1] + 1))
        # センターを塗るか(モーキャプで真っ黒になるの対策)
        is_paint_center = (fnos[-1] / len(fnos)) > 3

        is_show_on = True
        for fidx, next_fno in enumerate(range(fnos[-1] + 1)):
            next_show_changes = [si for si in motion.showiks if si.fno == next_fno]
            if next_show_changes:
                is_show_on = next_show_changes[0].show

            if not is_show_on:
                # 非表示だったら描画しない
                continue

            center_bf = motion.calc_bf("センター", next_fno)
            groove_bf = motion.calc_bf("グルーブ", next_fno)

            # 1Fごとに頂点を生成する
            next_global_3ds = MServiceUtils.calc_global_pos(base_model, target_links, motion, next_fno)
            tail_pos = next_global_3ds["グルーブ"]

            if fidx == 0:
                from_pos = tail_pos.copy()
                continue

            pidx = 0 if is_paint_center and (center_bf.read or groove_bf.read) else fidx

            # FROMからTOまで面を生成
            v1 = Vertex(
                index=len(model.vertex_dict),
                position=from_pos,
                normal=NORMAL_VEC,
                uv=MVector2D(uvs[pidx], 0.5),
                extended_uvs=[],
                deform=ROOT_BDEF1,
                edge_factor=0,
            )
            model.vertex_dict[v1.index] = v1

            v2 = Vertex(
                index=len(model.vertex_dict),
                position=tail_pos,
                normal=NORMAL_VEC,
                uv=MVector2D(uvs[pidx], 0.5),
                extended_uvs=[],
                deform=ROOT_BDEF1,
                edge_factor=0,
            )
            model.vertex_dict[v2.index] = v2

            v3 = Vertex(
                index=len(model.vertex_dict),
                position=from_pos + MVector3D(WIDTH, 0, 0),
                normal=NORMAL_VEC,
                uv=MVector2D(uvs[pidx], 0.5),
                extended_uvs=[],
                deform=ROOT_BDEF1,
                edge_factor=0,
            )
            model.vertex_dict[v3.index] = v3

            v4 = Vertex(
                index=len(model.vertex_dict),
                position=tail_pos + MVector3D(WIDTH, 0, 0),
                normal=NORMAL_VEC,
                uv=MVector2D(uvs[pidx], 0.5),
                extended_uvs=[],
                deform=ROOT_BDEF1,
                edge_factor=0,
            )
            model.vertex_dict[v4.index] = v4

            # v5 = Vertex(
            #     index=len(model.vertex_dict),
            #     position=from_pos + MVector3D(WIDTH, WIDTH, 0),
            #     normal=NORMAL_VEC,
            #     uv=MVector2D(uvs[pidx], 0.5),
            #     extended_uvs=[],
            #     deform=ROOT_BDEF1,
            #     edge_factor=0,
            # )
            # model.vertex_dict[v5.index] = v5

            # v6 = Vertex(
            #     index=len(model.vertex_dict),
            #     position=tail_pos + MVector3D(WIDTH, WIDTH, 0),
            #     normal=NORMAL_VEC,
            #     uv=MVector2D(uvs[pidx], 0.5),
            #     extended_uvs=[],
            #     deform=ROOT_BDEF1,
            #     edge_factor=0,
            # )
            # model.vertex_dict[v6.index] = v6

            # v7 = Vertex(
            #     index=len(model.vertex_dict),
            #     position=from_pos + MVector3D(0, 0, WIDTH),
            #     normal=NORMAL_VEC,
            #     uv=MVector2D(uvs[pidx], 0.5),
            #     extended_uvs=[],
            #     deform=ROOT_BDEF1,
            #     edge_factor=0,
            # )
            # model.vertex_dict[v7.index] = v7

            # v8 = Vertex(
            #     index=len(model.vertex_dict),
            #     position=tail_pos + MVector3D(0, 0, WIDTH),
            #     normal=NORMAL_VEC,
            #     uv=MVector2D(uvs[pidx], 0.5),
            #     extended_uvs=[],
            #     deform=ROOT_BDEF1,
            #     edge_factor=0,
            # )
            # model.vertex_dict[v8.index] = v8

            model.indices[len(model.indices)] = [v1.index, v2.index, v3.index]
            model.indices[len(model.indices)] = [v3.index, v2.index, v4.index]
            # model.indices[len(model.indices)] = [v3.index, v4.index, v5.index]
            # model.indices[len(model.indices)] = [v5.index, v4.index, v6.index]
            # model.indices[len(model.indices)] = [v5.index, v6.index, v7.index]
            # model.indices[len(model.indices)] = [v7.index, v6.index, v8.index]
            # model.indices[len(model.indices)] = [v7.index, v8.index, v1.index]
            # model.indices[len(model.indices)] = [v1.index, v8.index, v2.index]
            model.materials[mat_name].vertex_count += 3 * 2

            # 処理が終わったら、ひとつ先に進める
            from_pos = tail_pos.copy()

            if fidx % 500 == 0:
                logger.count(f"【軌跡モデル生成】", next_fno, fnos)

        return True, model
