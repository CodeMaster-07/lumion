from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import discord


PANEL_COLOR = discord.Color.from_rgb(0, 229, 255)
USAGE_COLOR = discord.Color.from_rgb(57, 255, 20)
PRICE_COLOR = discord.Color.from_rgb(255, 43, 214)
PURCHASE_COLOR = discord.Color.from_rgb(255, 111, 0)
PURCHASE_NOTICE = "## 모든 구매문의는 <@1053641807310901288> 으로 DM 부탁드립니다"


@dataclass(frozen=True)
class PanelConfig:
    brand_name: str
    brand_logo_url: str
    panel_image_url: str | None
    purchase_url: str | None
    panel_log_webhook_url: str | None


def load_panel_config(brand_name: str, brand_logo_url: str, default_panel_image_url: str | None) -> PanelConfig:
    purchase_url = os.getenv("DISCORD_PURCHASE_URL", "").strip() or None
    panel_log_webhook_url = (
        os.getenv(
            "DISCORD_PANEL_LOG_WEBHOOK_URL",
            "",
        ).strip()
        or None
    )
    panel_image_url = (
        os.getenv(
            "DISCORD_PANEL_IMAGE_URL",
            "https://cdn.discordapp.com/attachments/1506982264926502943/1510536081777492118/content.png?ex=6a1d2bda&is=6a1bda5a&hm=57828d20b03a9e71e8fd45fd1256816b6f58561746a3d0937719cb502037166c&",
        ).strip()
        or default_panel_image_url
    )
    return PanelConfig(
        brand_name=brand_name,
        brand_logo_url=brand_logo_url,
        panel_image_url=panel_image_url,
        purchase_url=purchase_url,
        panel_log_webhook_url=panel_log_webhook_url,
    )


def _set_branding(embed: discord.Embed, config: PanelConfig, *, show_image: bool) -> discord.Embed:
    embed.set_footer(text=config.brand_name, icon_url=config.brand_logo_url)
    if show_image and config.panel_image_url:
        embed.set_image(url=config.panel_image_url)
    return embed


def build_panel_embed(config: PanelConfig) -> discord.Embed:
    embed = discord.Embed(
        title="홍보봇 이용 안내",
        description=(
            "**이용방법, 가격표, 구매 안내를 버튼으로 바로 확인하실 수 있습니다.**\n"
            "> 버튼을 누르면 해당 안내가 나만 보이는 메시지로 표시됩니다."
        ),
        color=PANEL_COLOR,
    )
    embed.add_field(
        name="안내 메뉴",
        value=(
            "`이용방법`  진행 방식과 이용 절차 안내\n"
            "`가격표`  플랜별 요금과 확장 할인 안내\n"
            "`구매하기`  구매 전 준비사항과 진행 순서 안내"
        ),
        inline=False,
    )
    return _set_branding(embed, config, show_image=True)


def build_usage_embed(config: PanelConfig) -> discord.Embed:
    embed = discord.Embed(
        title="이용방법 안내",
        description=(
            "**홍보봇은 아래 순서대로 간단하게 이용하실 수 있습니다.**\n"
            "> 필요한 정보만 전달해주시면 확인 후 순서대로 진행됩니다."
        ),
        color=USAGE_COLOR,
    )
    embed.add_field(
        name="1. 이용 정보 전달",
        value="홍보할 서버와 원하는 플랜 또는 봇 수, 운영 방향을 전달해주시면 됩니다.",
        inline=False,
    )
    embed.add_field(
        name="2. 확인 및 세팅",
        value="전달해주신 내용 확인 후 홍보 문구, 전송 흐름, 운영 구성을 세팅합니다.",
        inline=False,
    )
    embed.add_field(
        name="3. 서비스 시작",
        value="세팅이 완료되면 자동 전송이 시작되며, 진행 상태는 로그를 통해 확인하실 수 있습니다.",
        inline=False,
    )
    return _set_branding(embed, config, show_image=False)


def build_price_embed(config: PanelConfig, data: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title="홍보봇 가격표",
        description=(
            "**1개부터 10개까지 할인된 월 요금입니다.**\n"
            "> 봇 수가 많을수록 더 큰 할인이 적용됩니다."
        ),
        color=PRICE_COLOR,
    )

    price_rows = [
        ("1개", "15,000원/월", "11,000원/월", "월 4,000원 할인", ""),
        ("2개", "27,000원/월", "20,000원/월", "월 7,000원 할인", ""),
        ("3개", "39,000원/월", "29,000원/월", "월 10,000원 할인", "BEST"),
        ("4개", "52,000원/월", "38,000원/월", "월 14,000원 할인", ""),
        ("5개", "65,000원/월", "47,000원/월", "월 18,000원 할인", ""),
        ("6개", "77,000원/월", "56,000원/월", "월 21,000원 할인", ""),
        ("7개", "89,000원/월", "65,000원/월", "월 24,000원 할인", ""),
        ("8개", "101,000원/월", "74,000원/월", "월 27,000원 할인", ""),
        ("9개", "113,000원/월", "83,000원/월", "월 30,000원 할인", ""),
        ("10개", "125,000원/월", "90,000원/월", "월 35,000원 할인", "최대 할인"),
    ]

    def format_rows(rows: list[tuple[str, str, str, str, str]]) -> str:
        formatted_rows = []
        for bots, original, discounted, saving, badge in rows:
            badge_text = f"  `{badge}`" if badge else ""
            formatted_rows.append(
                f"**{bots}**{badge_text}\n"
                f"~~{original}~~ → **{discounted}**\n"
                f"`{saving}`"
            )
        return "\n\n".join(formatted_rows)

    embed.add_field(name="1~5개 요금", value=format_rows(price_rows[:5]), inline=False)
    embed.add_field(name="6~10개 요금", value=format_rows(price_rows[5:]), inline=False)
    embed.add_field(
        name="11개 이상",
        value="운영 규모에 맞춘 별도 할인 견적을 안내해드립니다.",
        inline=False,
    )

    return _set_branding(embed, config, show_image=False)


def build_purchase_embed(config: PanelConfig) -> discord.Embed:
    embed = discord.Embed(
        title="구매 안내",
        description=(
            "**구매 전 아래 내용만 준비해주시면 빠르게 안내 도와드립니다.**\n"
            "> 확인이 끝나면 순서대로 진행 후 서비스가 시작됩니다."
        ),
        color=PURCHASE_COLOR,
    )
    embed.add_field(
        name="구매 전 준비사항",
        value=(
            "• 봇 갯수\n"
            "• 플랜\n"
            "• 이용하실 일수\n"
            "• 봇 프로필 이미지\n"
            "• 봇 닉네임\n"
            "• 전송할 홍보 멘트"
        ),
        inline=False,
    )
    embed.add_field(
        name="진행 순서",
        value=(
            "1. 구매 문의 및 구성 확인\n"
            "2. 안내 후 결제 진행\n"
            "3. 확인 완료 후 서비스 시작"
        ),
        inline=False,
    )
    if config.purchase_url:
        embed.add_field(name="문의 바로가기", value=f"[구매 문의하기]({config.purchase_url})", inline=False)

    return _set_branding(embed, config, show_image=False)


class PanelView(discord.ui.View):
    def __init__(self, config: PanelConfig, data: dict[str, Any]) -> None:
        super().__init__(timeout=None)
        self.config = config
        self.data = data

    async def log_panel_click(self, interaction: discord.Interaction, button_name: str) -> None:
        webhook_url = self.config.panel_log_webhook_url
        if webhook_url is None:
            return

        client = interaction.client
        if client is None or not hasattr(client, "send_webhook_log"):
            return

        try:
            user = interaction.user
            source_channel = getattr(interaction.channel, "mention", "알 수 없는 채널")
            await client.send_webhook_log(
                webhook_url,
                f"📌 {user.mention} ({user}) 님이 {source_channel} 에서 `{button_name}` 버튼을 클릭했습니다."
            )
        except Exception as exc:
            print(f"Failed to log panel click for {button_name}: {exc}")

    @discord.ui.button(
        label="이용방법",
        style=discord.ButtonStyle.secondary,
        emoji="📘",
        custom_id="lumion_panel_usage",
    )
    async def usage_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await interaction.response.send_message(
            embed=build_usage_embed(self.config),
            ephemeral=True,
        )
        await self.log_panel_click(interaction, "이용방법")

    @discord.ui.button(
        label="가격표",
        style=discord.ButtonStyle.primary,
        emoji="💎",
        custom_id="lumion_panel_price",
    )
    async def price_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await interaction.response.send_message(
            embed=build_price_embed(self.config, self.data),
            ephemeral=True,
        )
        await self.log_panel_click(interaction, "가격표")

    @discord.ui.button(
        label="구매하기",
        style=discord.ButtonStyle.success,
        emoji="🛒",
        custom_id="lumion_panel_purchase",
    )
    async def purchase_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        del button
        await interaction.response.send_message(
            content=PURCHASE_NOTICE,
            embed=build_purchase_embed(self.config),
            ephemeral=True,
        )
        await self.log_panel_click(interaction, "구매하기")
