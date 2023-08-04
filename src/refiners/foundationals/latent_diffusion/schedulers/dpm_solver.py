from refiners.foundationals.latent_diffusion.schedulers.scheduler import Scheduler
import numpy as np
from torch import Tensor, device as Device, tensor, exp
from collections import deque


class DPMSolver(Scheduler):
    """Implements DPM-Solver++ from https://arxiv.org/abs/2211.01095

    We only support noise prediction for now.
    """

    def __init__(
        self,
        num_inference_steps: int,
        num_train_timesteps: int = 1_000,
        initial_diffusion_rate: float = 8.5e-4,
        final_diffusion_rate: float = 1.2e-2,
        device: Device | str = "cpu",
    ):
        super().__init__(
            num_inference_steps=num_inference_steps,
            num_train_timesteps=num_train_timesteps,
            initial_diffusion_rate=initial_diffusion_rate,
            final_diffusion_rate=final_diffusion_rate,
            device=device,
        )
        self.estimated_data = deque([tensor([])] * 2, maxlen=2)
        self.initial_steps = 0

    def _generate_timesteps(self) -> Tensor:
        # We need to use numpy here because:
        # numpy.linspace(0,999,31)[15] is 499.49999999999994
        # torch.linspace(0,999,31)[15] is 499.5
        # ...and we want the same result as the original codebase.
        return tensor(
            np.linspace(0, self.num_train_timesteps - 1, self.num_inference_steps + 1).round().astype(int)[1:],
            device=self.device,
        ).flip(0)

    def dpm_solver_first_order_update(self, x: Tensor, noise: Tensor, step: int) -> Tensor:
        timestep, previous_timestep = (
            self.timesteps[step],
            self.timesteps[step + 1 if step < len(self.timesteps) - 1 else 0],
        )
        previous_ratio, current_ratio = (
            self.signal_to_noise_ratios[previous_timestep],
            self.signal_to_noise_ratios[timestep],
        )
        previous_scale_factor = self.cumulative_scale_factors[previous_timestep]
        previous_noise_std, current_noise_std = (
            self.noise_std[previous_timestep],
            self.noise_std[timestep],
        )
        exp_factor = exp(-(previous_ratio - current_ratio))
        denoised_x = (previous_noise_std / current_noise_std) * x - (previous_scale_factor * (exp_factor - 1.0)) * noise
        return denoised_x

    def multistep_dpm_solver_second_order_update(self, x: Tensor, step: int) -> Tensor:
        previous_timestep, current_timestep, next_timestep = (
            self.timesteps[step + 1] if step < len(self.timesteps) - 1 else tensor([0]),
            self.timesteps[step],
            self.timesteps[step - 1],
        )
        current_data_estimation, next_data_estimation = self.estimated_data[-1], self.estimated_data[-2]
        previous_ratio, current_ratio, next_ratio = (
            self.signal_to_noise_ratios[previous_timestep],
            self.signal_to_noise_ratios[current_timestep],
            self.signal_to_noise_ratios[next_timestep],
        )
        previous_scale_factor = self.cumulative_scale_factors[previous_timestep]
        previous_std, current_std = (
            self.noise_std[previous_timestep],
            self.noise_std[current_timestep],
        )
        estimation_delta = (current_data_estimation - next_data_estimation) / (
            (current_ratio - next_ratio) / (previous_ratio - current_ratio)
        )
        exp_neg_factor = exp(-(previous_ratio - current_ratio))
        x_t = (
            (previous_std / current_std) * x
            - (previous_scale_factor * (exp_neg_factor - 1.0)) * current_data_estimation
            - 0.5 * (previous_scale_factor * (exp_neg_factor - 1.0)) * estimation_delta
        )
        return x_t

    def __call__(
        self,
        x: Tensor,
        noise: Tensor,
        step: int,
    ) -> Tensor:
        """
        Represents one step of the backward diffusion process that iteratively denoises the input data `x`.

        This method works by estimating the denoised version of `x` and applying either a first-order or second-order
        backward Euler update, which is a numerical method commonly used to solve ordinary differential equations
        (ODEs).
        """
        current_timestep = self.timesteps[step]
        scale_factor, noise_ratio = self.cumulative_scale_factors[current_timestep], self.noise_std[current_timestep]
        estimated_denoised_data = (x - noise_ratio * noise) / scale_factor
        self.estimated_data.append(estimated_denoised_data)
        denoised_x = (
            self.dpm_solver_first_order_update(x=x, noise=estimated_denoised_data, step=step)
            if (self.initial_steps == 0)
            else self.multistep_dpm_solver_second_order_update(x=x, step=step)
        )
        if self.initial_steps < 2:
            self.initial_steps += 1
        return denoised_x