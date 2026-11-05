"""The three models students edit during the lesson."""
import torch
from torch import nn


def mlp(input_dim, output_dim, hidden=48):
    return nn.Sequential(nn.Linear(input_dim, hidden), nn.Tanh(),
                         nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, output_dim))


class Autoencoder(nn.Module):
    def __init__(self, input_dim, latent_dim):
        super().__init__()
        self.encoder = mlp(input_dim, latent_dim)
        self.decoder = mlp(latent_dim, input_dim)

    def forward(self, x):
        return self.decoder(self.encoder(x))


class LatentTranslator(nn.Module):
    """Encoders/decoder frozen; learn only sim latent -> sensor latent."""
    def __init__(self, sim_ae, sensor_ae, sim_latent=8, sensor_latent=4):
        super().__init__()
        self.sim_encoder = sim_ae.encoder
        self.sensor_encoder = sensor_ae.encoder
        self.sensor_decoder = sensor_ae.decoder
        for module in (self.sim_encoder, self.sensor_encoder, self.sensor_decoder):
            module.requires_grad_(False)
        self.mapping = mlp(sim_latent, sensor_latent, hidden=32)
        self.register_buffer("sensor_latent_scale", torch.ones(sensor_latent))

    def latent(self, x):
        return self.mapping(self.sim_encoder(x))

    def forward(self, x):
        return self.sensor_decoder(self.latent(x))

    def objective(self, x, sensor_window):
        z_pred = self.latent(x)
        with torch.no_grad():
            z_target = self.sensor_encoder(sensor_window)
        latent_loss = ((z_pred - z_target) / self.sensor_latent_scale).square().mean()
        reconstruction = (self.sensor_decoder(z_pred) - sensor_window).square().mean()
        return reconstruction + .1 * latent_loss
