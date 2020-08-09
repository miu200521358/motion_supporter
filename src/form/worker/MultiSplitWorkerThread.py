# -*- coding: utf-8 -*-
#

import os
import wx
import time
import gc
from form.worker.BaseWorkerThread import BaseWorkerThread, task_takes_time
from mmd.PmxData import PmxModel
from service.ConvertMultiSplitService import ConvertMultiSplitService
from module.MOptions import MMultiSplitOptions
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class MultiSplitWorkerThread(BaseWorkerThread):

    def __init__(self, frame: wx.Frame, result_event: wx.Event, is_exec_saving: bool):
        self.elapsed_time = 0
        self.frame = frame
        self.result_event = result_event
        self.gauge_ctrl = frame.multi_split_panel_ctrl.gauge_ctrl
        self.is_exec_saving = is_exec_saving
        self.options = None

        super().__init__(frame, self.result_event, frame.multi_split_panel_ctrl.console_ctrl)

    @task_takes_time
    def thread_event(self):
        start = time.time()

        self.result = self.frame.multi_split_panel_ctrl.multi_split_vmd_file_ctrl.load() and self.result

        dummy_model = PmxModel()
        dummy_model.name = "ゆらぎモデル"

        if self.result:
            self.options = MMultiSplitOptions(\
                version_name=self.frame.version_name, \
                logging_level=self.frame.logging_level, \
                motion=self.frame.multi_split_panel_ctrl.multi_split_vmd_file_ctrl.data, \
                model=dummy_model, \
                multi_split_size=self.frame.multi_split_panel_ctrl.multi_split_size_ctrl.GetValue(), \
                copy_cnt=self.frame.multi_split_panel_ctrl.copy_cnt_ctrl.GetValue(), \
                output_path=self.frame.multi_split_panel_ctrl.output_multi_split_vmd_file_ctrl.file_ctrl.GetPath(), \
                monitor=self.frame.multi_split_panel_ctrl.console_ctrl, \
                is_file=False, \
                outout_datetime=logger.outout_datetime, \
                max_workers=(1 if self.is_exec_saving else min(32, os.cpu_count() + 4)))
            
            self.result = ConvertMultiSplitService(self.options).execute() and self.result

        self.elapsed_time = time.time() - start

    def thread_delete(self):
        del self.options
        gc.collect()
        
    def post_event(self):
        wx.PostEvent(self.frame, self.result_event(result=self.result, elapsed_time=self.elapsed_time))
