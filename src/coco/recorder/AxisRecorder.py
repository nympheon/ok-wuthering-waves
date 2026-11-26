from ok import Logger, TriggerTask

from src.task.task_icons import task_icon
from .hooks import install_hooks
from .manual import ManualDriver
from .recording import QUALITY, Recorder


logger = Logger.get_logger(__name__)


class AxisRecorderTask(TriggerTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Combat Axis Recorder'
        self.description = ('Record local combat inputs, switching, recognition, logs and game frames for replay. '
                            'Manual recording uses the native PC game window with Auto Combat turned off.')
        self.icon = task_icon('diagnosis')
        self.trigger_interval = 0.15
        self.recorder = None
        self.manual = None
        self.default_config.update({
            '_enabled': False,
            'Recording mode': 'Automatic',
            'Record other combat tasks': False,
            'Record combat recognition': True,
            'Record combat logs': True,
            'Combat recording media': 'Images',
            'Combat recording quality': 'High',
            'Save recognition crops': False,
            'Keep combat recordings': 50,
            'Keep combat media': 5,
            'Manual recording hotkey': 'F7',
            'Start manual recording on enemy': False,
            'Manual idle seconds': 5,
        })
        self.config_type.update({
            'Recording mode': {'type': 'drop_down', 'options': ['Automatic', 'Manual']},
            'Combat recording media': {'type': 'drop_down', 'options': ['Off', 'Images', 'Video']},
            'Combat recording quality': {'type': 'drop_down', 'options': list(QUALITY)},
            'Manual recording hotkey': {'type': 'drop_down', 'options': ['F6', 'F7', 'F8', 'F10', 'F11']},
        })
        self.config_description.update({
            'Recording mode': 'Automatic follows game automation. Manual follows your own combat inputs.',
            'Record other combat tasks': 'Include battles from on-demand tasks such as farming Echoes.',
            'Record combat recognition': 'Save feature matches, OCR, color ratios, cooldowns and Concerto readings.',
            'Record combat logs': 'Save the automation thread’s logs during each recorded battle.',
            'Combat recording media': 'Images save about four frames per second. Video saves up to twelve.',
            'Combat recording quality': 'Standard uses up to 960 px wide, High uses up to 1600 px, and Original uses the full resolution.',
            'Save recognition crops': 'Save full-resolution crops for recorded recognition results.',
            'Keep combat recordings': 'Keep this many recent timelines under logs/axis_runs.',
            'Keep combat media': 'Keep images, video and crops for this many recent recordings.',
            'Manual recording hotkey': 'Start or stop recording while the native PC game has focus.',
            'Start manual recording on enemy': 'Start when an enemy is detected. The manual hotkey can still start or stop recording.',
            'Manual idle seconds': 'Finish enemy-started recordings after this long without an enemy or attack.',
        })

    @property
    def manual_mode(self):
        return self.config.get('Recording mode') == 'Manual'

    def accepts_automatic(self, task):
        return (self.enabled and not self.manual_mode and
                (self.config.get('Record other combat tasks') or type(task).__name__ == 'AutoCombatTask'))

    def recording_settings(self):
        config = self.config
        keep = max(1, config.get('Keep combat recordings'))
        quality = config.get('Combat recording quality')
        return {'reads': config.get('Record combat recognition'), 'logs': config.get('Record combat logs'),
                'media': config.get('Combat recording media'), 'quality': quality if quality in QUALITY else 'High',
                'crops': config.get('Save recognition crops'), 'keep': keep,
                'keep_media': min(keep, max(1, config.get('Keep combat media')))}

    def on_create(self):
        super().on_create()
        self.recorder = Recorder(self)
        self.manual = ManualDriver(self)
        install_hooks()

    def run(self):
        if self.manual_mode:
            self.trigger_interval = 0.09
            self.manual.tick()
        else:
            self.trigger_interval = 0.8
            self.manual.stop('Recording mode changed')
        # This trigger only observes; it leaves the current scheduler order intact.
        return False

    def disable(self):
        super().disable()
        if self.manual is not None:
            self.manual.stop('Recorder disabled')
        if self.recorder is not None:
            self.recorder.stop('Recorder disabled')

    def on_destroy(self):
        if self.manual is not None:
            self.manual.stop('Application closed')
        if self.recorder is not None:
            self.recorder.shutdown()
