import torch
import pytest

from typing import Iterator

from warnings import warn
from PIL import Image
from pathlib import Path

from refiners.fluxion.utils import load_from_safetensors, image_to_tensor, manual_seed
from refiners.foundationals.latent_diffusion import StableDiffusion_1, StableDiffusion_1_Inpainting
from refiners.foundationals.latent_diffusion.unet import UNet
from refiners.foundationals.latent_diffusion.controlnet import Controlnet
from refiners.foundationals.latent_diffusion.lora import LoraWeights
from refiners.foundationals.latent_diffusion.schedulers import DDIM
from refiners.foundationals.latent_diffusion.self_attention_injection import SelfAttentionInjection

from tests.utils import ensure_similar_images


@pytest.fixture(scope="module")
def ref_path(test_e2e_path: Path) -> Path:
    return test_e2e_path / "test_diffusion_ref"


@pytest.fixture(scope="module")
def cutecat_init(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "cutecat_init.png").convert("RGB")


@pytest.fixture(scope="module")
def kitchen_dog(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "kitchen_dog.png").convert("RGB")


@pytest.fixture(scope="module")
def kitchen_dog_mask(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "kitchen_dog_mask.png").convert("RGB")


@pytest.fixture
def expected_image_std_random_init(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "expected_std_random_init.png").convert("RGB")


@pytest.fixture
def expected_image_std_init_image(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "expected_std_init_image.png").convert("RGB")


@pytest.fixture
def expected_image_std_inpainting(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "expected_std_inpainting.png").convert("RGB")


@pytest.fixture(scope="module", params=["canny", "depth", "lineart", "normals", "sam"])
def controlnet_data(
    ref_path: Path, test_weights_path: Path, request: pytest.FixtureRequest
) -> Iterator[tuple[str, Image.Image, Image.Image, Path]]:
    cn_name: str = request.param
    condition_image = Image.open(ref_path / f"cutecat_guide_{cn_name}.png").convert("RGB")
    expected_image = Image.open(ref_path / f"expected_controlnet_{cn_name}.png").convert("RGB")
    weights_fn = {
        "depth": "lllyasviel_control_v11f1p_sd15_depth",
        "canny": "lllyasviel_control_v11p_sd15_canny",
        "lineart": "lllyasviel_control_v11p_sd15_lineart",
        "normals": "lllyasviel_control_v11p_sd15_normalbae",
        "sam": "mfidabel_controlnet-segment-anything",
    }

    weights_path = test_weights_path / "controlnet" / f"{weights_fn[cn_name]}.safetensors"
    yield (cn_name, condition_image, expected_image, weights_path)


@pytest.fixture(scope="module")
def controlnet_data_canny(ref_path: Path, test_weights_path: Path) -> tuple[str, Image.Image, Image.Image, Path]:
    cn_name = "canny"
    condition_image = Image.open(ref_path / f"cutecat_guide_{cn_name}.png").convert("RGB")
    expected_image = Image.open(ref_path / f"expected_controlnet_{cn_name}.png").convert("RGB")
    weights_path = test_weights_path / "controlnet" / "lllyasviel_control_v11p_sd15_canny.safetensors"
    return cn_name, condition_image, expected_image, weights_path


@pytest.fixture(scope="module")
def lora_data_pokemon(ref_path: Path, test_weights_path: Path) -> tuple[Image.Image, Path]:
    expected_image = Image.open(ref_path / "expected_lora_pokemon.png").convert("RGB")
    weights_path = test_weights_path / "loras" / "pcuenq_pokemon_lora.safetensors"
    return expected_image, weights_path


@pytest.fixture
def scene_image_inpainting_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "inpainting-scene.png").convert("RGB")


@pytest.fixture
def mask_image_inpainting_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "inpainting-mask.png").convert("RGB")


@pytest.fixture
def target_image_inpainting_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "inpainting-target.png").convert("RGB")


@pytest.fixture
def expected_image_inpainting_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "expected_inpainting_refonly.png").convert("RGB")


@pytest.fixture
def expected_image_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "expected_refonly.png").convert("RGB")


@pytest.fixture
def condition_image_refonly(ref_path: Path) -> Image.Image:
    return Image.open(ref_path / "cyberpunk_guide.png").convert("RGB")


@pytest.fixture(scope="module")
def text_encoder_weights(test_weights_path: Path) -> Path:
    text_encoder_weights = test_weights_path / "CLIPTextEncoderL.safetensors"
    if not text_encoder_weights.is_file():
        warn(f"could not find weights at {text_encoder_weights}, skipping")
        pytest.skip(allow_module_level=True)
    return text_encoder_weights


@pytest.fixture(scope="module")
def lda_weights(test_weights_path: Path) -> Path:
    lda_weights = test_weights_path / "lda.safetensors"
    if not lda_weights.is_file():
        warn(f"could not find weights at {lda_weights}, skipping")
        pytest.skip(allow_module_level=True)
    return lda_weights


@pytest.fixture(scope="module")
def unet_weights_std(test_weights_path: Path) -> Path:
    unet_weights_std = test_weights_path / "unet.safetensors"
    if not unet_weights_std.is_file():
        warn(f"could not find weights at {unet_weights_std}, skipping")
        pytest.skip(allow_module_level=True)
    return unet_weights_std


@pytest.fixture(scope="module")
def unet_weights_inpainting(test_weights_path: Path) -> Path:
    unet_weights_inpainting = test_weights_path / "inpainting" / "unet.safetensors"
    if not unet_weights_inpainting.is_file():
        warn(f"could not find weights at {unet_weights_inpainting}, skipping")
        pytest.skip(allow_module_level=True)
    return unet_weights_inpainting


@pytest.fixture
def sd15_std(
    text_encoder_weights: Path, lda_weights: Path, unet_weights_std: Path, test_device: torch.device
) -> StableDiffusion_1:
    if test_device.type == "cpu":
        warn("not running on CPU, skipping")
        pytest.skip()

    sd15 = StableDiffusion_1(device=test_device)

    sd15.clip_text_encoder.load_state_dict(load_from_safetensors(text_encoder_weights))
    sd15.lda.load_state_dict(load_from_safetensors(lda_weights))
    sd15.unet.load_state_dict(load_from_safetensors(unet_weights_std))

    return sd15


@pytest.fixture
def sd15_std_float16(
    text_encoder_weights: Path, lda_weights: Path, unet_weights_std: Path, test_device: torch.device
) -> StableDiffusion_1:
    if test_device.type == "cpu":
        warn("not running on CPU, skipping")
        pytest.skip()

    sd15 = StableDiffusion_1(device=test_device, dtype=torch.float16)

    sd15.clip_text_encoder.load_state_dict(load_from_safetensors(text_encoder_weights))
    sd15.lda.load_state_dict(load_from_safetensors(lda_weights))
    sd15.unet.load_state_dict(load_from_safetensors(unet_weights_std))

    return sd15


@pytest.fixture
def sd15_inpainting(
    text_encoder_weights: Path, lda_weights: Path, unet_weights_inpainting: Path, test_device: torch.device
) -> StableDiffusion_1_Inpainting:
    if test_device.type == "cpu":
        warn("not running on CPU, skipping")
        pytest.skip()

    unet = UNet(in_channels=9, clip_embedding_dim=768)
    sd15 = StableDiffusion_1_Inpainting(unet=unet, device=test_device)

    sd15.clip_text_encoder.load_state_dict(load_from_safetensors(text_encoder_weights))
    sd15.lda.load_state_dict(load_from_safetensors(lda_weights))
    sd15.unet.load_state_dict(load_from_safetensors(unet_weights_inpainting))

    return sd15


@pytest.fixture
def sd15_inpainting_float16(
    text_encoder_weights: Path, lda_weights: Path, unet_weights_inpainting: Path, test_device: torch.device
) -> StableDiffusion_1_Inpainting:
    if test_device.type == "cpu":
        warn("not running on CPU, skipping")
        pytest.skip()

    unet = UNet(in_channels=9, clip_embedding_dim=768)
    sd15 = StableDiffusion_1_Inpainting(unet=unet, device=test_device, dtype=torch.float16)

    sd15.clip_text_encoder.load_state_dict(load_from_safetensors(text_encoder_weights))
    sd15.lda.load_state_dict(load_from_safetensors(lda_weights))
    sd15.unet.load_state_dict(load_from_safetensors(unet_weights_inpainting))

    return sd15


@pytest.fixture
def sd15_ddim(
    text_encoder_weights: Path, lda_weights: Path, unet_weights_std: Path, test_device: torch.device
) -> StableDiffusion_1:
    if test_device.type == "cpu":
        warn("not running on CPU, skipping")
        pytest.skip()

    ddim_scheduler = DDIM(num_inference_steps=20)
    sd15 = StableDiffusion_1(scheduler=ddim_scheduler, device=test_device)

    sd15.clip_text_encoder.load_state_dict(load_from_safetensors(text_encoder_weights))
    sd15.lda.load_state_dict(load_from_safetensors(lda_weights))
    sd15.unet.load_state_dict(load_from_safetensors(unet_weights_std))

    return sd15


@torch.no_grad()
def test_diffusion_std_random_init(
    sd15_std: StableDiffusion_1, expected_image_std_random_init: Image.Image, test_device: torch.device
):
    sd15 = sd15_std
    n_steps = 30

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image_std_random_init)


@torch.no_grad()
def test_diffusion_std_random_init_float16(
    sd15_std_float16: StableDiffusion_1, expected_image_std_random_init: Image.Image, test_device: torch.device
):
    sd15 = sd15_std_float16
    n_steps = 30

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    assert clip_text_embedding.dtype == torch.float16
    assert negative_clip_text_embedding.dtype == torch.float16

    sd15.set_num_inference_steps(n_steps)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device, dtype=torch.float16)

    with torch.no_grad():
        for step in sd15.steps:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image_std_random_init, min_psnr=35, min_ssim=0.98)


@torch.no_grad()
def test_diffusion_std_init_image(
    sd15_std: StableDiffusion_1,
    cutecat_init: Image.Image,
    expected_image_std_init_image: Image.Image,
):
    sd15 = sd15_std
    n_steps = 35
    first_step = 5

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)

    manual_seed(2)
    x = sd15.init_latents((512, 512), cutecat_init, first_step=first_step)

    with torch.no_grad():
        for step in sd15.steps[first_step:]:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image_std_init_image)


@torch.no_grad()
def test_diffusion_inpainting(
    sd15_inpainting: StableDiffusion_1_Inpainting,
    kitchen_dog: Image.Image,
    kitchen_dog_mask: Image.Image,
    expected_image_std_inpainting: Image.Image,
    test_device: torch.device,
):
    sd15 = sd15_inpainting
    n_steps = 30

    prompt = "a large white cat, detailed high-quality professional image, sitting on a chair, in a kitchen"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)
    sd15.set_inpainting_conditions(kitchen_dog, kitchen_dog_mask)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    # PSNR and SSIM values are large because with float32 we get large differences even v.s. ourselves.
    ensure_similar_images(predicted_image, expected_image_std_inpainting, min_psnr=25, min_ssim=0.95)


@torch.no_grad()
def test_diffusion_inpainting_float16(
    sd15_inpainting_float16: StableDiffusion_1_Inpainting,
    kitchen_dog: Image.Image,
    kitchen_dog_mask: Image.Image,
    expected_image_std_inpainting: Image.Image,
    test_device: torch.device,
):
    sd15 = sd15_inpainting_float16
    n_steps = 30

    prompt = "a large white cat, detailed high-quality professional image, sitting on a chair, in a kitchen"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    assert clip_text_embedding.dtype == torch.float16
    assert negative_clip_text_embedding.dtype == torch.float16

    sd15.set_num_inference_steps(n_steps)
    sd15.set_inpainting_conditions(kitchen_dog, kitchen_dog_mask)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device, dtype=torch.float16)

    with torch.no_grad():
        for step in sd15.steps:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    # PSNR and SSIM values are large because float16 is even worse than float32.
    ensure_similar_images(predicted_image, expected_image_std_inpainting, min_psnr=20, min_ssim=0.92)


@torch.no_grad()
def test_diffusion_controlnet(
    sd15_std: StableDiffusion_1,
    controlnet_data: tuple[str, Image.Image, Image.Image, Path],
    test_device: torch.device,
):
    sd15 = sd15_std
    n_steps = 30

    cn_name, condition_image, expected_image, cn_weights_path = controlnet_data

    if not cn_weights_path.is_file():
        warn(f"could not find weights at {cn_weights_path}, skipping")
        pytest.skip(allow_module_level=True)

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)

    controlnet_state_dict = load_from_safetensors(cn_weights_path)
    controlnet = Controlnet(name=cn_name, device=test_device)
    controlnet.load_state_dict(controlnet_state_dict)
    controlnet.set_scale(0.5)
    sd15.unet.insert(0, controlnet)

    cn_condition = image_to_tensor(condition_image.convert("RGB"), device=test_device)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            controlnet.set_controlnet_condition(cn_condition)
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image, min_psnr=35, min_ssim=0.98)


@torch.no_grad()
def test_diffusion_controlnet_structural_copy(
    sd15_std: StableDiffusion_1,
    controlnet_data_canny: tuple[str, Image.Image, Image.Image, Path],
    test_device: torch.device,
):
    sd15_base = sd15_std
    sd15 = sd15_base.structural_copy()
    n_steps = 30

    cn_name, condition_image, expected_image, cn_weights_path = controlnet_data_canny

    if not cn_weights_path.is_file():
        warn(f"could not find weights at {cn_weights_path}, skipping")
        pytest.skip(allow_module_level=True)

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)

    controlnet_state_dict = load_from_safetensors(cn_weights_path)
    controlnet = Controlnet(name=cn_name, device=test_device)
    controlnet.load_state_dict(controlnet_state_dict)
    controlnet.set_scale(0.5)
    sd15.unet.insert(0, controlnet)

    cn_condition = image_to_tensor(condition_image.convert("RGB"), device=test_device)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            controlnet.set_controlnet_condition(cn_condition)
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image, min_psnr=35, min_ssim=0.98)


@torch.no_grad()
def test_diffusion_controlnet_float16(
    sd15_std_float16: StableDiffusion_1,
    controlnet_data_canny: tuple[str, Image.Image, Image.Image, Path],
    test_device: torch.device,
):
    sd15 = sd15_std_float16
    n_steps = 30

    cn_name, condition_image, expected_image, cn_weights_path = controlnet_data_canny

    if not cn_weights_path.is_file():
        warn(f"could not find weights at {cn_weights_path}, skipping")
        pytest.skip(allow_module_level=True)

    prompt = "a cute cat, detailed high-quality professional image"
    negative_prompt = "lowres, bad anatomy, bad hands, cropped, worst quality"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)
        negative_clip_text_embedding = sd15.compute_text_embedding(negative_prompt)

    sd15.set_num_inference_steps(n_steps)

    controlnet_state_dict = load_from_safetensors(cn_weights_path)
    controlnet = Controlnet(name=cn_name, device=test_device, dtype=torch.float16)
    controlnet.load_state_dict(controlnet_state_dict)
    controlnet.set_scale(0.5)
    sd15.unet.insert(0, controlnet)

    cn_condition = image_to_tensor(condition_image.convert("RGB"), device=test_device, dtype=torch.float16)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device, dtype=torch.float16)

    with torch.no_grad():
        for step in sd15.steps:
            controlnet.set_controlnet_condition(cn_condition)
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                negative_clip_text_embedding=negative_clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image, min_psnr=35, min_ssim=0.98)


@torch.no_grad()
def test_diffusion_lora(
    sd15_std: StableDiffusion_1,
    lora_data_pokemon: tuple[Image.Image, Path],
    test_device: torch.device,
):
    sd15 = sd15_std
    n_steps = 30

    expected_image, lora_weights_path = lora_data_pokemon

    if not lora_weights_path.is_file():
        warn(f"could not find weights at {lora_weights_path}, skipping")
        pytest.skip(allow_module_level=True)

    prompt = "a cute cat"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)

    sd15.set_num_inference_steps(n_steps)

    lora_weights = LoraWeights(lora_weights_path, device=test_device)
    lora_weights.patch(sd15, scale=1.0)

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image, min_psnr=35, min_ssim=0.98)


@torch.no_grad()
def test_diffusion_refonly(
    sd15_ddim: StableDiffusion_1,
    condition_image_refonly: Image.Image,
    expected_image_refonly: Image.Image,
    test_device: torch.device,
):
    sd15 = sd15_ddim
    prompt = "Chicken"

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)

    sai = SelfAttentionInjection(sd15.unet)
    sai.inject()

    guide = sd15.lda.encode_image(condition_image_refonly)
    guide = torch.cat((guide, guide))

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            noise = torch.randn(2, 4, 64, 64, device=test_device)
            noised_guide = sd15.scheduler.add_noise(guide, noise, step)
            sai.set_controlnet_condition(noised_guide)
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                condition_scale=7.5,
            )
            torch.randn(2, 4, 64, 64, device=test_device)  # for SD Web UI reproductibility only
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image_refonly, min_psnr=35, min_ssim=0.99)


@torch.no_grad()
def test_diffusion_inpainting_refonly(
    sd15_inpainting: StableDiffusion_1_Inpainting,
    scene_image_inpainting_refonly: Image.Image,
    target_image_inpainting_refonly: Image.Image,
    mask_image_inpainting_refonly: Image.Image,
    expected_image_inpainting_refonly: Image.Image,
    test_device: torch.device,
):
    sd15 = sd15_inpainting
    n_steps = 30
    prompt = ""  # unconditional

    with torch.no_grad():
        clip_text_embedding = sd15.compute_text_embedding(prompt)

    sai = SelfAttentionInjection(sd15.unet)
    sai.inject()

    sd15.set_num_inference_steps(n_steps)
    sd15.set_inpainting_conditions(target_image_inpainting_refonly, mask_image_inpainting_refonly)

    refonly_guide = sd15.lda.encode_image(scene_image_inpainting_refonly)
    refonly_guide = torch.cat((refonly_guide, refonly_guide))

    manual_seed(2)
    x = torch.randn(1, 4, 64, 64, device=test_device)

    with torch.no_grad():
        for step in sd15.steps:
            refonly_noise = torch.randn_like(refonly_guide)
            refonly_noised_guide = sd15.scheduler.add_noise(refonly_guide, refonly_noise, step)
            # See https://github.com/Mikubill/sd-webui-controlnet/pull/1275 ("1.1.170 reference-only begin to support
            # inpaint variation models")
            refonly_noised_guide = torch.cat(
                [refonly_noised_guide, torch.zeros_like(refonly_noised_guide)[:, 0:1, :, :], refonly_guide], dim=1
            )

            sai.set_controlnet_condition(refonly_noised_guide)
            x = sd15(
                x,
                step=step,
                clip_text_embedding=clip_text_embedding,
                condition_scale=7.5,
            )
        predicted_image = sd15.lda.decode_latents(x)

    ensure_similar_images(predicted_image, expected_image_inpainting_refonly, min_psnr=35, min_ssim=0.99)