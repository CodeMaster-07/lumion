import argparse
import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

from panel_views import PanelView, build_panel_embed, load_panel_config
from promo_split import register_promo_feature, process_promo_message


load_dotenv()


def parse_env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def parse_time_of_day_minutes(value: str, env_name: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        raise RuntimeError(f"{env_name} must use HH:MM format, for example 09:00.")

    hour = int(match.group(1))
    minute = int(match.group(2))

    if minute < 0 or minute > 59:
        raise RuntimeError(f"{env_name} minute must be between 00 and 59.")

    if env_name.endswith("_END") and hour == 24 and minute == 0:
        return 24 * 60

    if hour < 0 or hour > 23:
        raise RuntimeError(f"{env_name} hour must be between 00 and 23.")

    return hour * 60 + minute


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "lumion_public_purchase_logs.json"

CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "1510511036208255096"))
MIN_DELAY_SECONDS = int(os.getenv("MIN_DELAY_SECONDS", "60"))
MAX_DELAY_SECONDS = int(os.getenv("MAX_DELAY_SECONDS", "3600"))
PURCHASE_LOG_TIMEZONE = os.getenv("PURCHASE_LOG_TIMEZONE", "Asia/Seoul").strip()
MIN_DAILY_PURCHASE_LOGS = int(os.getenv("MIN_DAILY_PURCHASE_LOGS", "2"))
MAX_DAILY_PURCHASE_LOGS = int(os.getenv("MAX_DAILY_PURCHASE_LOGS", "8"))
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
PRESENCE_ACTIVITY_TEXT = os.getenv("PRESENCE_ACTIVITY_TEXT", "24시간 깨어있는중").strip()
BRAND_NAME = os.getenv("DISCORD_BRAND_NAME", "홍보봇.com").strip()
BRAND_LOGO_URL = os.getenv(
    "DISCORD_BRAND_LOGO_URL",
    "https://cdn.discordapp.com/attachments/1502363835451965491/1510500926228533440/2026-05-08_11.52.53.png?ex=6a1d0b1c&is=6a1bb99c&hm=e251d637de07c0e9f3d03924606a0ca9915f8f5a7cbd4dc69e5944edab34b9c2&",
).strip()
EXCLUDED_MESSAGE_GROUPS = {"trial_to_paid_conversion"}
DEFAULT_EMBED_IMAGE_URLS = [
    "https://cdn.discordapp.com/attachments/1506982264926502943/1510509596312076329/image.png?ex=6a1d132f&is=6a1bc1af&hm=5b89e7a95aa297838aa0568eca7a6e1d5ca73fd7ad7d79056ab1bb493ef58bcd&",
    "https://cdn.discordapp.com/attachments/1506982264926502943/1510510338485915848/content.png?ex=6a1d13e0&is=6a1bc260&hm=2ffec434d42c6157f0d443708a34ed9c43bf4a029d30ce10ce91e033c80141e7&",
    "https://cdn.discordapp.com/attachments/1506982264926502943/1510510737469083668/content.png?ex=6a1d143f&is=6a1bc2bf&hm=4381a74fc49d7388f1a78b0194fc338cf25537e248a53d3863a361bb52f4f0de&",
    "https://cdn.discordapp.com/attachments/1506982264926502943/1510512030442979358/content.png?ex=6a1d1574&is=6a1bc3f4&hm=cc40fbdb9d51d49f5c36c4ad8ff1759c4dd5fa5d99e3d12ca38a62c9e4d96516&",
]
ENABLE_MESSAGE_COMMAND = parse_env_bool("ENABLE_MESSAGE_CONTENT_INTENT", False)

# 역할 자동 부여는 기본 활성화입니다.
# 끄고 싶으면 .env 에 ENABLE_AUTO_ROLE=0 을 넣으세요.
ENABLE_AUTO_ROLE = parse_env_bool("ENABLE_AUTO_ROLE", True)

# on_member_join 이벤트를 받으려면 코드 인텐트와 Discord Developer Portal의
# SERVER MEMBERS INTENT가 둘 다 켜져 있어야 합니다.
ENABLE_MEMBERS_INTENT = parse_env_bool("ENABLE_MEMBERS_INTENT", ENABLE_AUTO_ROLE)

AUTO_ROLE_GUILD_ID = parse_env_int("AUTO_ROLE_GUILD_ID", 1240496858175111259)
AUTO_ROLE_ID = parse_env_int("AUTO_ROLE_ID", 1501517681151574076)
AUTO_ROLE_LOG_WEBHOOK_URL = os.getenv("AUTO_ROLE_LOG_WEBHOOK_URL", "").strip() or None

# 구매로그 발송 시간대입니다. 기본값은 KST 기준 09:00~23:50입니다.
# 24시간 랜덤 발송을 원하면 PURCHASE_LOG_ACTIVE_START=00:00,
# PURCHASE_LOG_ACTIVE_END=24:00 으로 설정하세요.
PURCHASE_LOG_ACTIVE_START = os.getenv("PURCHASE_LOG_ACTIVE_START", "09:00").strip()
PURCHASE_LOG_ACTIVE_END = os.getenv("PURCHASE_LOG_ACTIVE_END", "23:50").strip()
PURCHASE_LOG_ACTIVE_START_MINUTE = parse_time_of_day_minutes(
    PURCHASE_LOG_ACTIVE_START,
    "PURCHASE_LOG_ACTIVE_START",
)
PURCHASE_LOG_ACTIVE_END_MINUTE = parse_time_of_day_minutes(
    PURCHASE_LOG_ACTIVE_END,
    "PURCHASE_LOG_ACTIVE_END",
)
PURCHASE_LOG_MIN_GAP_SECONDS = parse_env_int("PURCHASE_LOG_MIN_GAP_SECONDS", MIN_DELAY_SECONDS)


if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is missing. Check your .env file.")

if MIN_DELAY_SECONDS > MAX_DELAY_SECONDS:
    raise RuntimeError("MIN_DELAY_SECONDS must be less than or equal to MAX_DELAY_SECONDS.")

if MIN_DAILY_PURCHASE_LOGS > MAX_DAILY_PURCHASE_LOGS:
    raise RuntimeError("MIN_DAILY_PURCHASE_LOGS must be less than or equal to MAX_DAILY_PURCHASE_LOGS.")

if MIN_DAILY_PURCHASE_LOGS < 0:
    raise RuntimeError("MIN_DAILY_PURCHASE_LOGS must be 0 or greater.")

if PURCHASE_LOG_MIN_GAP_SECONDS < 0:
    raise RuntimeError("PURCHASE_LOG_MIN_GAP_SECONDS must be 0 or greater.")

if PURCHASE_LOG_ACTIVE_START_MINUTE == PURCHASE_LOG_ACTIVE_END_MINUTE:
    raise RuntimeError("PURCHASE_LOG_ACTIVE_START and PURCHASE_LOG_ACTIVE_END cannot be the same.")


@dataclass
class TemplateMessage:
    group: str
    title: str
    content: str


@dataclass
class ParsedContent:
    heading: str | None
    description_lines: list[str]
    detail_fields: list[tuple[str, str]]
    feature_lines: list[str]


@dataclass
class RuntimeOptions:
    burst_count: int
    burst_delay_seconds: float


def load_message_data() -> dict[str, Any]:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_runtime_options() -> RuntimeOptions:
    parser = argparse.ArgumentParser(description="LumiOn Discord promotion bot")
    parser.add_argument(
        "--burst",
        type=int,
        default=0,
        help="Send this many test embeds in a row, then exit.",
    )
    parser.add_argument(
        "--burst-delay",
        type=float,
        default=1.5,
        help="Seconds to wait between burst test embeds.",
    )
    args = parser.parse_args()

    if args.burst < 0:
        parser.error("--burst must be 0 or greater.")
    if args.burst_delay < 0:
        parser.error("--burst-delay must be 0 or greater.")

    return RuntimeOptions(
        burst_count=args.burst,
        burst_delay_seconds=args.burst_delay,
    )


def build_placeholder_context(data: dict[str, Any]) -> dict[str, str]:
    plans = data.get("plans", {})
    full_price_table = data.get("full_price_table", [])
    plan_key = random.choice(list(plans)) if plans else None
    plan = plans.get(plan_key, {})
    selected_price = random.choice(full_price_table) if full_price_table else {}

    plan_name = plan.get("name", "스탠다드")
    plan_emoji = plan.get("emoji", "🚀")
    plan_badge = f" {plan['badge']}" if plan.get("badge") else ""
    bots = selected_price.get("bots", plan.get("bots", "3봇"))
    price = selected_price.get("monthly_price", plan.get("monthly_price", "39,000원"))

    return {
        "{플랜명}": f"{plan_emoji} {plan_name}{plan_badge}".strip(),
        "{봇수}": bots,
        "{가격}": f"월 {price}" if "월" not in price else price,
        "{베이직수}": str(random.randint(1, 4)),
        "{스탠다드수}": str(random.randint(1, 5)),
        "{프리미엄수}": str(random.randint(1, 3)),
        "{추가봇수}": str(random.randint(1, 15)),
        "{신규수}": str(random.randint(1, 8)),
        "{연장수}": str(random.randint(1, 6)),
        "{업그레이드수}": str(random.randint(1, 4)),
        "{전환수}": str(random.randint(1, 4)),
        "{구매수}": str(random.randint(3, 18)),
    }


def collect_templates(data: dict[str, Any]) -> list[TemplateMessage]:
    messages = data.get("messages", {})
    templates: list[TemplateMessage] = []

    for group_name, group_items in messages.items():
        if group_name in EXCLUDED_MESSAGE_GROUPS:
            continue

        if not isinstance(group_items, list):
            continue

        for item in group_items:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title", "")).strip()
            content = str(item.get("content", "")).strip()
            if title and content:
                templates.append(TemplateMessage(group=group_name, title=title, content=content))

    if not templates:
        raise RuntimeError("No message templates were found in lumion_public_purchase_logs.json.")

    return templates


def fill_placeholders(text: str, context: dict[str, str]) -> str:
    for key, value in context.items():
        text = text.replace(key, value)
    return text


def parse_template_content(content: str) -> ParsedContent:
    heading: str | None = None
    description_lines: list[str] = []
    detail_fields: list[tuple[str, str]] = []
    feature_lines: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# "):
            heading = line[2:].strip()
            continue

        line = line.replace("`", "")
        if line.startswith("' "):
            body = line[2:].strip()
            if ":" in body:
                name, value = body.split(":", 1)
                detail_fields.append((name.strip(), value.strip()))
            else:
                feature_lines.append(body)
            continue

        description_lines.append(line)

    return ParsedContent(
        heading=heading,
        description_lines=description_lines,
        detail_fields=detail_fields,
        feature_lines=feature_lines,
    )


def select_embed_color(text: str) -> discord.Color:
    if "프리미엄" in text:
        return discord.Color.from_rgb(255, 43, 214)
    if "베이직" in text:
        return discord.Color.from_rgb(57, 255, 20)
    if "스탠다드" in text or "BEST" in text:
        return discord.Color.from_rgb(0, 229, 255)
    return random.choice(
        [
            discord.Color.from_rgb(0, 229, 255),
            discord.Color.from_rgb(57, 255, 20),
            discord.Color.from_rgb(255, 43, 214),
            discord.Color.from_rgb(255, 111, 0),
        ]
    )


def compact_text(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line).strip()


def build_daily_purchase_schedule(now: datetime) -> list[datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start = day_start + timedelta(minutes=PURCHASE_LOG_ACTIVE_START_MINUTE)
    window_end = day_start + timedelta(minutes=PURCHASE_LOG_ACTIVE_END_MINUTE)

    # 종료 시간이 시작 시간보다 빠르면 자정을 넘기는 시간대로 처리합니다.
    # 예: 22:00~02:00
    if window_end <= window_start:
        window_end += timedelta(days=1)

    available_start = max(now + timedelta(seconds=1), window_start)
    if available_start >= window_end:
        return []

    send_count = random.randint(MIN_DAILY_PURCHASE_LOGS, MAX_DAILY_PURCHASE_LOGS)
    if send_count <= 0:
        return []

    total_seconds = int((window_end - available_start).total_seconds())
    if total_seconds <= 0:
        return []

    if PURCHASE_LOG_MIN_GAP_SECONDS > 0 and send_count > 1:
        max_possible_count = (total_seconds // PURCHASE_LOG_MIN_GAP_SECONDS) + 1
        send_count = min(send_count, max_possible_count)

    if send_count <= 0:
        return []

    min_gap = PURCHASE_LOG_MIN_GAP_SECONDS if send_count > 1 else 0
    required_gap_seconds = min_gap * (send_count - 1)

    if required_gap_seconds > total_seconds:
        min_gap = max(0, total_seconds // max(1, send_count - 1))
        required_gap_seconds = min_gap * (send_count - 1)

    # 정렬된 랜덤 base offset에 최소 간격을 더해, 같은 시간대에 몰리는 현상을 줄입니다.
    random_span = max(0, total_seconds - required_gap_seconds)
    base_offsets = sorted(random.randint(0, random_span) for _ in range(send_count))

    schedule = [
        available_start + timedelta(seconds=base_offset + index * min_gap)
        for index, base_offset in enumerate(base_offsets)
    ]

    return [send_time for send_time in schedule if send_time > now]


def load_embed_image_urls() -> list[str]:
    raw_value = os.getenv("DISCORD_EMBED_IMAGE_URLS", "").strip()
    if not raw_value:
        return DEFAULT_EMBED_IMAGE_URLS[:]

    urls = [item.strip() for item in re.split(r"[\n,]+", raw_value) if item.strip()]
    return urls or DEFAULT_EMBED_IMAGE_URLS[:]


def normalize_detail_name(name: str) -> str:
    normalized = re.sub(r"\s+", "", name)
    return normalized


def split_detail_fields(detail_fields: list[tuple[str, str]]) -> tuple[dict[str, str], list[tuple[str, str]]]:
    details: dict[str, str] = {}
    extras: list[tuple[str, str]] = []

    for name, value in detail_fields:
        key = normalize_detail_name(name)
        if key in {"플랜", "봇개수", "봇수", "월이용료", "가격", "월요금", "상태", "구성", "용도", "구매자"}:
            details[key] = value
        else:
            extras.append((name, value))

    return details, extras


def build_purchase_description(title_text: str, description_lines: list[str], details: dict[str, str]) -> str:
    accent = random.choice(
        [
            "실시간 구매 로그가 반영되었습니다.",
            "새로운 자동화 세팅이 접수되었습니다.",
            "브랜드 운영 흐름에 맞춘 주문이 확인되었습니다.",
        ]
    )
    headline = description_lines[0] if description_lines else accent
    subline = description_lines[1] if len(description_lines) > 1 else accent
    plan = details.get("플랜", details.get("구성", "맞춤 구성"))

    return "\n".join(
        [
            f"**{title_text}**",
            f"> {headline}",
            f"> {subline}",
            "",
            f"`LIVE STATUS`  {plan}",
        ]
    ).strip()


def build_summary_description(title_text: str, description_lines: list[str]) -> str:
    accent = description_lines[0] if description_lines else "오늘 집계된 LumiOn 운영 현황입니다."
    tail = description_lines[1] if len(description_lines) > 1 else "실시간 흐름을 한눈에 볼 수 있게 정리했습니다."
    return "\n".join(
        [
            f"**{title_text}**",
            f"> {accent}",
            f"> {tail}",
        ]
    ).strip()


def add_key_fields(embed: discord.Embed, details: dict[str, str]) -> None:
    plan_value = details.get("플랜", details.get("구성", "맞춤 구성"))
    bots_value = details.get("봇개수", details.get("봇수", details.get("구성", "자동 구성")))
    price_value = details.get("월이용료", details.get("가격", details.get("월요금", "문의")))
    status_value = details.get("상태", "서비스 시작")
    if status_value == "세팅 진행 중":
        status_value = "서비스 시작"

    field_rows = [
        ("플랜", f"`{plan_value}`"),
        ("구성", f"`{bots_value}`"),
        ("이용료", f"`{price_value}`"),
        ("상태", f"`{status_value}`"),
    ]

    for name, value in field_rows:
        embed.add_field(name=name, value=value, inline=True)


class LumiOnBot(discord.Client):
    def __init__(
        self,
        templates: list[TemplateMessage],
        data: dict[str, Any],
        runtime_options: RuntimeOptions,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = ENABLE_MESSAGE_COMMAND
        intents.members = ENABLE_MEMBERS_INTENT
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ready_diagnostics_printed = False
        self.templates = templates
        self.data = data
        self.runtime_options = runtime_options
        self.sender_task: asyncio.Task[None] | None = None
        self.webhook_session: aiohttp.ClientSession | None = None
        self.embed_image_urls = load_embed_image_urls()
        self.image_rotation: list[str] = []
        self.last_image_url: str | None = None
        default_panel_image_url = self.embed_image_urls[0] if self.embed_image_urls else None
        self.panel_config = load_panel_config(
            brand_name=BRAND_NAME,
            brand_logo_url=BRAND_LOGO_URL,
            default_panel_image_url=default_panel_image_url,
        )
        self.persistent_panel_view = PanelView(config=self.panel_config, data=self.data)
        self.tree.command(
            name="패널",
            description="홍보봇 안내 패널을 현재 채널에 올립니다.",
        )(self.post_panel_slash)
        self.tree.command(
            name="역할테스트",
            description="자동 역할 부여 설정을 점검하고 지정 멤버에게 역할을 부여합니다.",
        )(self.test_auto_role_slash)
        # 홍보지 반자르기 기능 (/홍보지, /홍보지패널, 채널 자동감지)
        self.promo_panel_view = register_promo_feature(
            self,
            brand_name=BRAND_NAME,
            brand_logo_url=BRAND_LOGO_URL,
            prefs_path=str(BASE_DIR / "promo_prefs.json"),
        )

    async def setup_hook(self) -> None:
        if self.webhook_session is None or self.webhook_session.closed:
            self.webhook_session = aiohttp.ClientSession()
        self.add_view(self.persistent_panel_view)
        self.add_view(self.promo_panel_view)
        # 글로벌 명령만 사용. 이전에 길드로 복사돼 중복(두 개씩)으로 뜨던 명령을 제거한다.
        main_guild_id = parse_env_int("DISCORD_MAIN_GUILD_ID", AUTO_ROLE_GUILD_ID)
        if main_guild_id:
            guild_obj = discord.Object(id=main_guild_id)
            self.tree.clear_commands(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)  # 길드 전용 명령 비우기 → 중복 해소
            print(f"Cleared guild-scoped commands for guild {main_guild_id} (dedupe).")
        await self.tree.sync()
        if self.sender_task is None:
            self.sender_task = asyncio.create_task(self.random_sender_loop())

    async def close(self) -> None:
        if self.webhook_session is not None and not self.webhook_session.closed:
            await self.webhook_session.close()
        await super().close()

    async def on_ready(self) -> None:
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name=PRESENCE_ACTIVITY_TEXT),
        )
        print(f"Presence set: {PRESENCE_ACTIVITY_TEXT}")
        print(f"Connected as {self.user} ({self.user.id})")
        guild_names = ", ".join(f"{guild.name} ({guild.id})" for guild in self.guilds) or "none"
        print(f"Visible guilds: {guild_names}")

        if ENABLE_MESSAGE_COMMAND:
            print("Message content intent command enabled: !패널")
        else:
            print("Slash command available: /패널")

        if ENABLE_AUTO_ROLE:
            if ENABLE_MEMBERS_INTENT:
                print("Members intent enabled in code: auto role assignment can receive join events.")
            else:
                print("Members intent disabled in code: auto role assignment cannot receive join events.")

            if not self.ready_diagnostics_printed:
                self.ready_diagnostics_printed = True
                await self.validate_auto_role_setup()
        else:
            print("Auto role assignment disabled by ENABLE_AUTO_ROLE=0.")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # 홍보지 채널에 올라온 이미지 자동 분할 (message_content 인텐트가 있을 때만 실제 동작)
        try:
            await process_promo_message(self, message)
        except Exception as exc:  # noqa: BLE001
            print(f"[promo] on_message 처리 오류: {exc}")

        if not ENABLE_MESSAGE_COMMAND:
            return

        if message.content.strip() != "!패널":
            return

        await self.send_panel_message(message.channel)

    async def post_panel_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=False)
        await self.send_panel_message(interaction.channel)
        await interaction.followup.send("패널을 이 채널에 올렸습니다.", ephemeral=True)

    async def test_auto_role_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=False)

        if interaction.guild is None:
            await interaction.followup.send("서버 안에서만 사용할 수 있습니다.", ephemeral=True)
            return

        if interaction.guild.id != AUTO_ROLE_GUILD_ID:
            await interaction.followup.send(
                f"현재 서버 ID `{interaction.guild.id}` 는 AUTO_ROLE_GUILD_ID `{AUTO_ROLE_GUILD_ID}` 와 다릅니다.",
                ephemeral=True,
            )
            return

        invoker = interaction.user
        if not isinstance(invoker, discord.Member) or not invoker.guild_permissions.manage_roles:
            await interaction.followup.send(
                "이 명령은 `역할 관리` 권한이 있는 관리자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        target_member = member or invoker
        success, message = await self.assign_auto_role(target_member, source="manual slash test")
        await interaction.followup.send(message, ephemeral=True)

    async def send_panel_message(self, channel: discord.abc.Messageable | None) -> None:
        if channel is None:
            return

        embed = build_panel_embed(self.panel_config)
        await channel.send(embed=embed, view=PanelView(config=self.panel_config, data=self.data))

    async def send_webhook_log(self, webhook_url: str | None, content: str) -> None:
        if not webhook_url:
            print(f"Webhook URL unavailable. Message was: {content}")
            return

        try:
            if self.webhook_session is None or self.webhook_session.closed:
                self.webhook_session = aiohttp.ClientSession()

            webhook = discord.Webhook.from_url(webhook_url, session=self.webhook_session)
            await webhook.send(
                content=content,
                username="홍보봇 로그",
                avatar_url=BRAND_LOGO_URL,
            )
        except discord.DiscordException as exc:
            print(f"Failed to send webhook log: {exc}")
            print(f"Original log message: {content}")
        except aiohttp.ClientError as exc:
            print(f"HTTP client error while sending webhook log: {exc}")
            print(f"Original log message: {content}")

    async def get_bot_member(self, guild: discord.Guild) -> discord.Member | None:
        if guild.me is not None:
            return guild.me

        if self.user is None:
            return None

        cached_member = guild.get_member(self.user.id)
        if cached_member is not None:
            return cached_member

        try:
            return await guild.fetch_member(self.user.id)
        except discord.DiscordException:
            return None

    async def validate_auto_role_setup(self) -> None:
        guild = self.get_guild(AUTO_ROLE_GUILD_ID)
        if guild is None:
            message = (
                f"❌ 자동 역할 설정 오류: 봇이 AUTO_ROLE_GUILD_ID `{AUTO_ROLE_GUILD_ID}` 서버를 볼 수 없습니다. "
                "봇이 해당 서버에 초대되어 있는지 확인하세요."
            )
            print(message)
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return

        role = guild.get_role(AUTO_ROLE_ID)
        if role is None:
            message = (
                f"❌ 자동 역할 설정 오류: `{guild.name}` 서버에서 AUTO_ROLE_ID `{AUTO_ROLE_ID}` 역할을 찾지 못했습니다."
            )
            print(message)
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return

        bot_member = await self.get_bot_member(guild)
        if bot_member is None:
            message = "❌ 자동 역할 설정 오류: 서버 안의 봇 멤버 정보를 가져오지 못했습니다."
            print(message)
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return

        problems: list[str] = []

        if not ENABLE_MEMBERS_INTENT:
            problems.append(
                "코드에서 ENABLE_MEMBERS_INTENT가 꺼져 있어 on_member_join 이벤트를 받을 수 없습니다."
            )

        if not bot_member.guild_permissions.manage_roles:
            problems.append("봇에게 `역할 관리` 권한이 없습니다.")

        if role.managed:
            problems.append("대상 역할이 연동/관리형 역할이라 봇이 직접 부여할 수 없습니다.")

        if bot_member.top_role.position <= role.position:
            problems.append(
                f"봇 최고 역할 `{bot_member.top_role.name}` 이 대상 역할 `{role.name}` 보다 위에 있지 않습니다."
            )

        if problems:
            message = "❌ 자동 역할 설정 점검 실패:\n" + "\n".join(f"- {item}" for item in problems)
            print(message)
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return

        message = (
            "✅ 자동 역할 설정 점검 완료: "
            f"서버 `{guild.name}`, 대상 역할 `{role.name}`, 봇 최고 역할 `{bot_member.top_role.name}`"
        )
        print(message)
        await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)

    async def assign_auto_role(self, member: discord.Member, source: str) -> tuple[bool, str]:
        if not ENABLE_AUTO_ROLE:
            return False, "자동 역할 부여가 ENABLE_AUTO_ROLE=0 으로 비활성화되어 있습니다."

        if not ENABLE_MEMBERS_INTENT:
            return False, "ENABLE_MEMBERS_INTENT가 꺼져 있어 자동 역할 부여 이벤트를 받을 수 없습니다."

        if member.guild.id != AUTO_ROLE_GUILD_ID:
            return False, (
                f"현재 서버 ID `{member.guild.id}` 는 AUTO_ROLE_GUILD_ID `{AUTO_ROLE_GUILD_ID}` 와 다릅니다."
            )

        role = member.guild.get_role(AUTO_ROLE_ID)
        if role is None:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: 역할 `{AUTO_ROLE_ID}` 을(를) 찾지 못했습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

        if role in member.roles:
            message = f"ℹ️ {member.mention} ({member}) 는 이미 {role.mention} 역할을 가지고 있습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return True, message

        bot_member = await self.get_bot_member(member.guild)
        if bot_member is None:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: 봇 멤버 정보를 가져오지 못했습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

        if not bot_member.guild_permissions.manage_roles:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: 봇에게 `역할 관리` 권한이 없습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

        if role.managed:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: {role.mention} 은 관리형 역할이라 직접 부여할 수 없습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

        if bot_member.top_role.position <= role.position:
            message = (
                f"❌ {member.mention} ({member}) 역할 부여 실패: 역할 순서 문제. "
                f"봇 최고 역할 `{bot_member.top_role.name}` 을 대상 역할 `{role.name}` 보다 위로 올려야 합니다."
            )
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

        try:
            await member.add_roles(role, reason=f"Auto role assignment on member join ({source})")
            message = f"✅ {member.mention} ({member}) 에게 {role.mention} 역할을 부여했습니다."
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return True, message
        except discord.Forbidden as exc:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: 권한 부족 또는 역할 순서 문제. {exc}"
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message
        except discord.HTTPException as exc:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: Discord API 오류. {exc}"
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message
        except Exception as exc:
            message = f"❌ {member.mention} ({member}) 역할 부여 실패: 예외 발생. {exc}"
            await self.send_webhook_log(AUTO_ROLE_LOG_WEBHOOK_URL, message)
            return False, message

    async def on_member_join(self, member: discord.Member) -> None:
        success, message = await self.assign_auto_role(member, source="member join")
        if not success:
            print(message)

    async def resolve_channel(self) -> discord.abc.Messageable | None:
        channel = self.get_channel(CHANNEL_ID)
        if channel is not None:
            return channel

        try:
            return await self.fetch_channel(CHANNEL_ID)
        except discord.DiscordException as exc:
            print(f"Failed to fetch channel {CHANNEL_ID}: {exc}")
            if self.guilds:
                for guild in self.guilds:
                    visible_channels = [
                        f"{channel.name} ({channel.id})"
                        for channel in guild.text_channels[:15]
                    ]
                    joined = ", ".join(visible_channels) or "no visible text channels"
                    print(f"Guild {guild.name} ({guild.id}) visible text channels: {joined}")
            return None

    def next_embed_image_url(self) -> str | None:
        if not self.embed_image_urls:
            return None

        if not self.image_rotation:
            self.image_rotation = self.embed_image_urls[:]
            random.shuffle(self.image_rotation)

            if (
                self.last_image_url is not None
                and len(self.image_rotation) > 1
                and self.image_rotation[0] == self.last_image_url
            ):
                self.image_rotation.append(self.image_rotation.pop(0))

        image_url = self.image_rotation.pop(0)
        self.last_image_url = image_url
        return image_url

    def build_embed(self) -> discord.Embed:
        template = random.choice(self.templates)
        placeholders = build_placeholder_context(self.data)
        filled_content = fill_placeholders(template.content, placeholders)
        parsed = parse_template_content(filled_content)
        title_text = parsed.heading or template.title
        details, _extras = split_detail_fields(parsed.detail_fields)

        if template.group == "daily_summary":
            body_text = build_summary_description(title_text, parsed.description_lines)
        else:
            body_text = build_purchase_description(title_text, parsed.description_lines, details)

        embed = discord.Embed(
            description=body_text,
            color=select_embed_color(f"{title_text}\n{filled_content}"),
            timestamp=discord.utils.utcnow(),
        )

        embed.set_footer(text=BRAND_NAME, icon_url=BRAND_LOGO_URL)
        image_url = self.next_embed_image_url()
        if image_url:
            embed.set_image(url=image_url)

        if template.group == "daily_summary":
            embed.title = "루미온 일일 현황"
            summary_lines = re.findall(r"([가-힣A-Za-z0-9 ]+:\s*[^\n]+)", filled_content)
            summary_lines = [line for line in summary_lines if "무료체험" not in line]
            summary_value = "\n".join(f"• {line}" for line in summary_lines[:5]) if summary_lines else "• 집계 데이터 없음"
            embed.add_field(name="오늘의 집계", value=summary_value, inline=False)
            return embed

        embed.title = "홍보봇 실시간 주문"

        add_key_fields(embed, details)
        return embed

    async def random_sender_loop(self) -> None:
        await self.wait_until_ready()
        channel = await self.resolve_channel()

        if channel is None:
            print("Target channel could not be resolved. Shutting down.")
            await self.close()
            return

        if self.runtime_options.burst_count > 0:
            print(
                f"Running burst test: {self.runtime_options.burst_count} embeds, "
                f"{self.runtime_options.burst_delay_seconds} seconds apart."
            )
            for index in range(self.runtime_options.burst_count):
                try:
                    embed = self.build_embed()
                    await channel.send(embed=embed)
                    print(
                        f"Sent burst embed {index + 1}/{self.runtime_options.burst_count} "
                        f"to channel {CHANNEL_ID}."
                    )
                except discord.DiscordException as exc:
                    print(f"Discord API error during burst test: {exc}")
                    break

                if index < self.runtime_options.burst_count - 1:
                    await asyncio.sleep(self.runtime_options.burst_delay_seconds)

            print("Burst test complete. Closing client.")
            await self.close()
            return

        tz = ZoneInfo(PURCHASE_LOG_TIMEZONE)
        schedule_date = None
        daily_schedule: list[datetime] = []

        while not self.is_closed():
            try:
                now = datetime.now(tz)

                if schedule_date != now.date():
                    schedule_date = now.date()
                    daily_schedule = build_daily_purchase_schedule(now)

                    readable_schedule = ", ".join(
                        send_time.strftime("%H:%M:%S") for send_time in daily_schedule
                    ) or "no remaining sends today"

                    print(
                        f"Generated purchase log schedule for {schedule_date}: "
                        f"{len(daily_schedule)} remaining sends -> {readable_schedule}"
                    )

                if not daily_schedule:
                    tomorrow = (now + timedelta(days=1)).replace(
                        hour=0, minute=0, second=5, microsecond=0
                    )
                    sleep_seconds = max(1, (tomorrow - now).total_seconds())

                    print(
                        f"Today's purchase log schedule is complete. "
                        f"Next schedule will be generated in {int(sleep_seconds)} seconds."
                    )

                    await asyncio.sleep(sleep_seconds)
                    continue

                next_send_at = daily_schedule.pop(0)
                sleep_seconds = max(0, (next_send_at - now).total_seconds())

                print(
                    f"Next purchase log scheduled at "
                    f"{next_send_at.strftime('%Y-%m-%d %H:%M:%S %Z')}. "
                    f"Sleeping for {int(sleep_seconds)} seconds."
                )

                await asyncio.sleep(sleep_seconds)

                embed = self.build_embed()
                await channel.send(embed=embed)

                print(
                    f"Sent scheduled purchase log to channel {CHANNEL_ID} at "
                    f"{datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}."
                )

            except discord.DiscordException as exc:
                print(f"Discord API error while sending scheduled purchase log: {exc}")
                await asyncio.sleep(30)
            except Exception as exc:
                print(f"Unexpected error while sending scheduled purchase log: {exc}")
                await asyncio.sleep(30)


def main() -> None:
    runtime_options = parse_runtime_options()
    data = load_message_data()
    templates = collect_templates(data)
    bot = LumiOnBot(templates=templates, data=data, runtime_options=runtime_options)
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
