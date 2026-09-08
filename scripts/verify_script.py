import asyncio, sys
sys.path.insert(0, r'D:\项目\novel-to-drama')
from app.engines.script_engine import generate_script

RAW = ("黄昏的客栈外，镖头沈厉牵马驻足。屋内小二探头喊：客官打尖还是住店？沈厉不答，只盯着檐角一只黑猫。"
"黑猫一跃而下，落地竟化成人影。那人冷笑：十年前你杀我兄长，今日讨债。沈厉握刀柄，刀未出鞘，风已起。"
"他忽然跃上屋顶，黑猫人紧随其后，脚步踏碎瓦片。巷中灯影摇动，二人隔街对峙。沈厉沉声：当年是你兄长先劫镖。"
"那人神色一滞，随即咬牙：镖可还，命难偿。话音未落袖中飞出一柄短刃。沈厉侧身避开，短刃钉入木柱。"
"黑猫人再攻，拳风带起尘土。沈厉旋身以刀背格挡，火星四溅。两人缠斗数合，难分胜负。忽然远处钟声大作，二人同时收势。"
"黑猫人喘息道：今日作罢，来日再分生死。说完纵身消失在夜色里。沈厉垂刀入鞘，牵马继续前行，月亮从云后露出半张脸。")

async def main():
    script = await generate_script(RAW)
    shots = [s for sc in script.scenes for s in sc.shots]
    print("title:", script.title, "| scenes:", len(script.scenes))
    print("total_shots:", len(shots))
    for i, s in enumerate(shots):
        dlg = " / ".join(f"{d.character}:{d.line}" for d in s.dialogues if d.line) or "-"
        narr = "Y" if s.narrator.strip() else "-"
        sfx = ",".join(e.get("name", "") for e in (s.sound_effects or [])) or "-"
        print(f"  shot{i}: dur={s.duration} narr={narr} dlg='{dlg[:24]}' sfx={sfx}")

asyncio.run(main())
