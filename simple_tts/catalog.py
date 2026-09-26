"""静态目录数据。

本模块只放"界面要展示的常量"，不含任何逻辑。数据来源：
https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5

界面上的可配置项与文档中的请求参数一一对应：
- model              -> MODELS
- audio.voice        -> PRESET_VOICES / SAMPLE_MIME
- audio.format       -> FORMATS
- user 消息           -> DIRECTOR_TEMPLATE、OPENING_STYLES（自然语言/标签两种控制）
- assistant 消息      -> INLINE_TAGS
"""

# ---------------------------------------------------------------- 模型

# tone_source 决定右侧「音色」区展示哪一块内容：
#   "preset"  -> 预置音色下拉
#   "design"  -> 无音色控件，改由 user 消息（音色描述）决定
#   "clone"   -> 音频样本文件选择
MODELS = [
    {
        "id": "mimo-v2.5-tts",
        "label": "预置音色  mimo-v2.5-tts",
        "short": "预置音色",
        "tone_source": "preset",
        "supports_sing": True,
        "supports_optimize": False,
        "requires_style_prompt": False,
        "desc": "使用预置精品音色合成，支持唱歌模式；不支持音色设计与音色复刻。",
    },
    {
        "id": "mimo-v2.5-tts-voicedesign",
        "label": "音色设计  mimo-v2.5-tts-voicedesign",
        "short": "音色设计",
        "tone_source": "design",
        "supports_sing": False,
        "supports_optimize": True,
        "requires_style_prompt": True,
        "desc": "通过文本描述定制音色，无需预置音色或音频样本；不支持唱歌模式。",
    },
    {
        "id": "mimo-v2.5-tts-voiceclone",
        "label": "音色复刻  mimo-v2.5-tts-voiceclone",
        "short": "音色复刻",
        "tone_source": "clone",
        "supports_sing": False,
        "supports_optimize": False,
        "requires_style_prompt": False,
        "desc": "基于音频样本复刻任意音色；不支持唱歌模式与音色设计。",
    },
]


def model_by_id(model_id: str) -> dict:
    """按 model id 取模型定义，未知 id 回落到第一个模型。"""
    for model in MODELS:
        if model["id"] == model_id:
            return model
    return MODELS[0]


# ---------------------------------------------------------------- 预置音色

# mimo_default 的实际音色因部署集群而异：中国集群为「冰糖」，其他集群为「Mia」。
PRESET_VOICES = [
    {"name": "MiMo-默认", "voice_id": "mimo_default", "language": "因集群而异", "gender": "—"},
    {"name": "冰糖", "voice_id": "冰糖", "language": "中文", "gender": "女"},
    {"name": "茉莉", "voice_id": "茉莉", "language": "中文", "gender": "女"},
    {"name": "苏打", "voice_id": "苏打", "language": "中文", "gender": "男"},
    {"name": "白桦", "voice_id": "白桦", "language": "中文", "gender": "男"},
    {"name": "Mia", "voice_id": "Mia", "language": "英文", "gender": "女"},
    {"name": "Chloe", "voice_id": "Chloe", "language": "英文", "gender": "女"},
    {"name": "Milo", "voice_id": "Milo", "language": "英文", "gender": "男"},
    {"name": "Dean", "voice_id": "Dean", "language": "英文", "gender": "男"},
]


def voice_label(voice: dict) -> str:
    """下拉框里显示的一行文本，例如「冰糖（中文·女）」。"""
    return f"{voice['name']}（{voice['language']}·{voice['gender']}）"


# ---------------------------------------------------------------- 输出格式

FORMATS = [
    ("wav", "WAV", "服务端返回成型 WAV 文件，无需自行补写文件头"),
    ("pcm16", "PCM16 裸流", "24kHz PCM16LE 单声道，仅流式场景需要拼接；本项目不使用"),
]

# ---------------------------------------------------------------- 音色复刻样本

# (扩展名, MIME 类型)。文档限定只支持 mp3 与 wav，Base64 后不超过 10MB。
SAMPLE_MIME = [
    (".mp3", "audio/mpeg"),
    (".wav", "audio/wav"),
]
MAX_SAMPLE_BYTES = 10 * 1024 * 1024


def sample_mime_for(path: str) -> str:
    """按扩展名取 MIME；未识别时按 wav 处理。"""
    lowered = path.lower()
    for ext, mime in SAMPLE_MIME:
        if lowered.endswith(ext):
            return mime
    return "audio/wav"


# ---------------------------------------------------------------- 风格标签

# 开头风格标签：写在文本最前面，形如「(风格1 风格2)正文」。
# 括号支持半角 ()、全角（）、方括号 []，分隔符不限。
OPENING_STYLES = [
    ("基础情绪", ["开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠"]),
    ("复合情绪", ["怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情"]),
    ("整体语调", ["温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉"]),
    ("音色定位", ["磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅"]),
    ("人设腔调", ["夹子音", "御姐音", "正太音", "大叔音", "台湾腔"]),
    ("方言", ["东北话", "四川话", "河南话", "粤语"]),
    ("角色扮演", ["孙悟空", "林黛玉"]),
]

# 唱歌不是普通风格：必须独占文本最开头的标签位置，且只能单独出现。
SING_STYLE = "唱歌"

# 行内音频标签：可插入文本任意位置，形如「[哽咽]」。
INLINE_TAGS = [
    ("语速与节奏", ["吸气", "深呼吸", "叹气", "长叹一口气", "喘息", "屏息"]),
    ("情绪状态", ["紧张", "害怕", "激动", "疲惫", "委屈", "撒娇", "心虚", "震惊", "不耐烦"]),
    ("语音特征", ["颤抖", "声音颤抖", "变调", "破音", "鼻音", "气声", "沙哑"]),
    ("哭笑表达", ["笑", "轻笑", "大笑", "冷笑", "抽泣", "呜咽", "哽咽", "嚎啕大哭"]),
]

# 开头风格标签的括号，三种写法等价，界面统一使用半角圆括号。
STYLE_BRACKETS = ["()", "（）", "[]"]

# ---------------------------------------------------------------- 自然语言控制

# 导演模式：user 消息里从「角色 / 场景 / 指导」三个维度刻画声线。
DIRECTOR_TEMPLATE = (
    "角色：\n"
    "场景：\n"
    "指导：\n"
    "语速与顿挫：\n"
    "气声与实声：\n"
    "咬字肌理："
)

# 音色设计描述的关键维度，作为输入框下方的示例提示。
VOICE_DESC_HINTS = [
    "性别与年龄：五十多岁的中年男性",
    "音色/质感：丝滑醇厚、带着磁性",
    "情绪/语气：温柔但带着一丝疲惫",
    "语速/节奏：语速极快，像连珠炮",
    "角色/人设：深夜电台 DJ",
    "场景描写：在给投资人路演",
    "年代参照：八十年代译制片配音",
]

# ---------------------------------------------------------------- 外部链接

DOC_URL = "https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5"
DEFAULT_API_BASE = "https://api.xiaomimimo.com/v1"
