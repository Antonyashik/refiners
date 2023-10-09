from refiners.foundationals.latent_diffusion.self_attention_guidance import (
    SAGAdapter,
    SelfAttentionShape,
    SelfAttentionMap,
)
from refiners.foundationals.latent_diffusion.stable_diffusion_1.unet import SD1UNet, MiddleBlock, ResidualBlock
from refiners.fluxion.layers.attentions import ScaledDotProductAttention
import refiners.fluxion.layers as fl


class SD1SAGAdapter(SAGAdapter[SD1UNet]):
    def __init__(self, target: SD1UNet, scale: float = 1.0, kernel_size: int = 9, sigma: float = 1.0) -> None:
        super().__init__(
            target=target,
            scale=scale,
            kernel_size=kernel_size,
            sigma=sigma,
        )

    def inject(self: "SD1SAGAdapter", parent: fl.Chain | None = None) -> "SD1SAGAdapter":
        middle_block = self.target.ensure_find(MiddleBlock)
        middle_block.insert_after_type(ResidualBlock, SelfAttentionShape(context_key="middle_block_attn_shape"))

        # An alternative would be to replace the ScaledDotProductAttention with a version which records the attention
        # scores to avoid computing these scores twice
        self_attn = middle_block.ensure_find(fl.SelfAttention)
        self_attn.insert_before_type(
            ScaledDotProductAttention,
            SelfAttentionMap(num_heads=self_attn.num_heads, context_key="middle_block_attn_map"),
        )

        return super().inject(parent)

    def eject(self) -> None:
        middle_block = self.target.ensure_find(MiddleBlock)
        middle_block.remove(middle_block.ensure_find(SelfAttentionShape))

        self_attn = middle_block.ensure_find(fl.SelfAttention)
        self_attn.remove(self_attn.ensure_find(SelfAttentionMap))

        super().eject()
