from abc import abstractmethod
from torch import Tensor, device as Device, dtype as DType, linspace, float32, sqrt, log
from typing import TypeVar

T = TypeVar("T", bound="Scheduler")


class Scheduler:
    """
    A base class for creating a diffusion model scheduler.

    The Scheduler creates a sequence of noise and scaling factors used in the diffusion process,
    which gradually transforms the original data distribution into a Gaussian one.

    This process is described using several parameters such as initial and final diffusion rates,
    and is encapsulated into a `__call__` method that applies a step of the diffusion process.
    """

    timesteps: Tensor

    def __init__(
        self,
        num_inference_steps: int,
        num_train_timesteps: int = 1_000,
        initial_diffusion_rate: float = 8.5e-4,
        final_diffusion_rate: float = 1.2e-2,
        device: Device | str = "cpu",
        dtype: DType = float32,
    ):
        self.device: Device = Device(device)
        self.dtype: DType = dtype
        self.num_inference_steps = num_inference_steps
        self.num_train_timesteps = num_train_timesteps
        self.initial_diffusion_rate = initial_diffusion_rate
        self.final_diffusion_rate = final_diffusion_rate
        self.scale_factors = (
            1.0
            - linspace(
                start=initial_diffusion_rate**0.5,
                end=final_diffusion_rate**0.5,
                steps=num_train_timesteps,
                dtype=dtype,
            )
            ** 2
        )
        self.cumulative_scale_factors = sqrt(self.scale_factors.cumprod(dim=0))
        self.noise_std = sqrt(1.0 - self.scale_factors.cumprod(dim=0))
        self.signal_to_noise_ratios = log(self.cumulative_scale_factors) - log(self.noise_std)
        self.timesteps = self._generate_timesteps()

    @abstractmethod
    def __call__(self, x: Tensor, noise: Tensor, step: int) -> Tensor:
        """
        Applies a step of the diffusion process to the input tensor `x` using the provided `noise` and `timestep`.

        This method should be overridden by subclasses to implement the specific diffusion process.
        """
        ...

    @abstractmethod
    def _generate_timesteps(self) -> Tensor:
        """
        Generates a tensor of timesteps.

        This method should be overridden by subclasses to provide the specific timesteps for the diffusion process.
        """
        ...

    @property
    def steps(self) -> list[int]:
        return list(range(self.num_inference_steps))

    def add_noise(
        self,
        x: Tensor,
        noise: Tensor,
        step: int,
    ) -> Tensor:
        timestep = self.timesteps[step]
        cumulative_scale_factors = self.cumulative_scale_factors[timestep].unsqueeze(-1).unsqueeze(-1)
        noise_stds = self.noise_std[timestep].unsqueeze(-1).unsqueeze(-1)
        noised_x = cumulative_scale_factors * x + noise_stds * noise
        return noised_x

    def to(self: T, device: Device | str | None = None, dtype: DType | None = None) -> T:  # type: ignore
        if device is not None:
            self.device = Device(device)
            self.timesteps = self.timesteps.to(device)
        if dtype is not None:
            self.dtype = dtype
        self.scale_factors = self.scale_factors.to(device, dtype=dtype)
        self.cumulative_scale_factors = self.cumulative_scale_factors.to(device, dtype=dtype)
        self.noise_std = self.noise_std.to(device, dtype=dtype)
        self.signal_to_noise_ratios = self.signal_to_noise_ratios.to(device, dtype=dtype)
        return self