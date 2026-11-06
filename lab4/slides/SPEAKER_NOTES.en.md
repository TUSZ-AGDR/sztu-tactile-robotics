# Lab 4 speaker notes: One sensor, two worlds

[Open English slides](index.en.html) · [Lab notebook](../practice.en.ipynb)

26 slides, approximately 30 minutes with discussion. Slide 2 provides references. For a shorter introduction, omit slides 4, 10, 15, 19 and 22. Press N for notes on the same display, or read this file on a separate device.

## 01. One sensor, two worlds

About 40 seconds. Let the contact replay run, then ask: if we can see a fingertip move near a surface in simulation, can we predict what the real tactile sensor reads? The left panel replays saved MuJoCo poses with measured SDK readings. The right panel shows a synthetic fixture-offset variant with generated sensor readings. Both panels are simulation renderings, not camera footage. Today we focus on ID3 at the index fingertip.

## 02. Before we begin

About 30 seconds. Say: This session is intended as a starting point for exploring the lab. I may not explain everything clearly, so please interrupt me with questions at any time. You can also ask the professor or Tengyuan (腾远), or use the courses below to continue learning. For neural-network foundations, start with the first three 3Blue1Brown lessons. The MIT course is optional further study in generative models. Official sources: https://diffusion.csail.mit.edu/2025/index.html ; https://arxiv.org/abs/2506.02070 ; https://www.3blue1brown.com/lessons/neural-networks/ ; https://www.3blue1brown.com/lessons/gradient-descent/ ; https://www.3blue1brown.com/lessons/backpropagation/

## 03. Why focus on ID3?

About 60 seconds. Whole-hand learning mixes many changing factors: pose, multiple contacts, control, and sensing. We hold the hand pose fixed and replay an existing trajectory. Motion still matters, but students do not need to learn a motion controller. This lets us examine what the tactile signal contains and how a model learns to predict it. The picture uses the supplied PAXINI left-hand URDF meshes, with ID3 on left_index_tactile_link3. It shows a neutral display pose for sensor localization, not a recorded replay posture; colors emphasize the selected sensor.

## 04. What changes during a touch?

About 45 seconds. Move the slider from separation to contact. Ask what else might change the measured signal even at the same position: speed, material, friction or earlier loading. The animation explains the question; it is not a physical sensor model.

## 05. One touch, three signals

About 60 seconds. These are actual raw packets from episode 5. Slide the time cursor and read the three numbers. A sensor gives measurements, not a photograph of contact. The units use the SDK conversion and are not a new metrological calibration. Time is relative to the recorded motion origin, so a few packets can precede zero.

## 06. Replay produces paired observations

About 70 seconds. Start with the supplied motion and ID3 measurements. MuJoCo replay produces local geometry and motion features. Match those features to sensor timestamps to form input-target pairs. Our sim2real task predicts sensor output from simulation features. It is not a grasp policy. Some original frames have zero simulator force, so proximity and motion features remain useful. Calibration belongs to data preparation; inference features must not depend on the force label being predicted.

## 07. The data you will use

About 45 seconds. There are five measured episodes containing 365 raw tactile packets. The practice dataset adds 300 synthetic sequences and 21,900 paired instants, with explicit provenance. These variants derive from the same five source motions. More rows help us practise, but they do not add independent measured evidence. Keep measured and synthetic scores separate.

## 08. A short history adds context

About 60 seconds. Switch between one and seven frames. A static position can be ambiguous, while the recent trajectory can show direction and response lag. Each frame has eleven simulation features; flattening seven frames gives 77 numbers. The MLP receives a fixed-size vector, not a recurrent state. Standardization is fitted on training data only.

## 09. Where does an MLP fit?

About 75 seconds. Machine learning means choosing model parameters from examples. A mean predictor ignores the input. Linear regression learns a weighted sum. An MLP composes learned transformations with nonlinear activations. It is a basic neural network, but it is not the simplest possible ML model. The notebook includes mean, zero and ridge baselines so we can check whether added complexity helps.

## 10. One neuron: mix, then transform

About 90 seconds. Use the slider to change x1 while x2 stays at 0.5. First calculate s = 1.2 x1 - 0.6 x2 + 0.2. Then apply tanh to get h. The weighted sum mixes inputs; the activation makes the response nonlinear. The weights and bias are the numbers training will change. These example inputs are standardized values, not physical force units. An individual hidden neuron need not represent a named physical property.

## 11. Layers build a prediction

About 90 seconds. A layer computes h = tanh(Wx + b). The next layer mixes these hidden values again. The real architecture has 48 neurons in each of two hidden layers; this drawing shows fewer for clarity. Nonlinear activations matter: stacking only linear layers still gives one linear map. The output layer has three unrestricted values because force components may be positive or negative. Hidden layers already learn internal representations. Later we will add an explicit small bottleneck and a reconstruction objective.

## 12. Training means reducing prediction error

About 90 seconds. A forward pass predicts the current three-axis force from a simulation window. Mean squared error averages squared differences between prediction and target. Backpropagation calculates gradients; Adam updates the trainable parameters. Repeat on the training set and select the checkpoint with the lowest validation loss. The reference code uses full-batch Adam. A lower training loss alone does not establish generalization. Scaling parameters also come only from the training set.

## 13. A prediction becomes more useful

About 60 seconds. Click through the fit illustration. The beginning is the training-mean baseline and the end is the saved MLP test prediction. Intermediate curves interpolate between them; they are not actual training checkpoints. Red segments show prediction differences. Ask whether the model captures onset, plateau and release, and what detail it misses.

## 14. Why introduce a latent space?

About 90 seconds. Direct regression is sufficient if our only goal is a force prediction and it works well. We introduce latent space to study representations: can a short code preserve useful information about a tactile history? We can inspect the code, change its size, reconstruct the signal, and learn a translation between modalities. These are motivations and testable hypotheses, not guarantees of improved accuracy or automatic domain adaptation. The encoder, decoder and translator in this lab are themselves small MLPs.

## 15. A curve can have a compact description

About 90 seconds. A bell-shaped curve can contain dozens of samples yet be generated by just amplitude and width, if its center is fixed. Move the sliders and ask students how many values they would need to transmit. This is the intuition behind a compact code. The actual tactile data are more complicated. An autoencoder learns its own coordinates; we do not tell it to discover these exact parameters or assume its axes have physical names.

## 16. An autoencoder learns to reconstruct

About 100 seconds. Let u be a 21-value sensor history. The encoder maps u to a four-value z, and the decoder maps z back to a 21-value reconstruction. Latent means hidden or inferred: z is calculated by the model rather than read directly from the sensor. The set of possible code vectors forms the latent space. Training minimizes the difference between the original and reconstruction. The target is the input itself, so this self-reconstruction task does not need simulation-sensor pairing. It still uses data and an objective; no manual class labels are required. In contrast, cross-modal translation later does require pairing. The displayed latent values are illustrative.

## 17. The bottleneck is a design choice

About 75 seconds. Ask what happens when sensor latent dimension changes from 2 to 4 to 8. A very small code can miss signal detail. A larger code can preserve more information but can also retain irrelevant variation or overfit. These are possible outcomes, not measured rankings. The input in this experiment is a 21-value history, not just three current forces. A standard autoencoder is not guaranteed to denoise. Compare dimensions on validation data and report both curves and errors.

## 18. What does a latent space look like?

About 75 seconds. This is an actual projection of sensor codes for the held-out episode. Color intensity shows target magnitude. PCA reduces four coordinates to two for display, so projected distances lose information. Nearby points may carry similar information, but reconstruction loss does not guarantee meaningful neighborhoods. A smooth or attractive scatterplot is not evidence of predictive accuracy. Training data alone determine the PCA basis.

## 19. Two encoders, two coordinate systems

About 90 seconds. Imagine two maps describing the same events with different coordinate systems. Separately trained autoencoders have no reason to align their axes. In this lab simulation codes have eight values and sensor codes four, so a direct coordinate equality would not even fit. We use paired windows to learn T from z_sim to z_sensor. The drawing uses two coordinates for illustration only. A translation is learned from examples and need not be invertible.

## 20. First, teach each side to reconstruct

About 75 seconds. Train one autoencoder on 77-value simulation windows with an eight-value latent, and another on 21-value sensor windows with a four-value latent. Each reconstructs its own input. This separates whether a representation can preserve its own modality from whether one modality predicts another. Evaluate reconstruction before blaming the mapping. Pretraining uses only training windows, with checkpoints chosen on validation.

## 21. Then learn the latent translation

About 120 seconds. Training uses the simulation encoder, mapper and sensor decoder along the upper path. The real sensor encoder supplies a latent target on the lower path. Only T is trainable after pretraining. The actual objective combines full sensor-window reconstruction MSE with 0.1 times a scaled latent matching MSE. Gradients pass through the frozen decoder to update T; frozen does not mean disconnected. Switch to inference: the real sensor branch is removed. With model-ready simulation features, no sensor target is read. This does not imply the measured motion and calibration used to prepare the dataset were label-free.

## 22. Where can reconstruction go wrong?

About 75 seconds. First check whether the sensor autoencoder reconstructs a real history from its own code. If not, inspect the bottleneck or autoencoder training. If it does, but translated predictions are poor, inspect the simulation representation, mapping, and information available in the simulation features. Friction or hysteresis may be only partially observed. A decoder cannot recover information that the upstream path did not preserve or predict. Compare these failure modes using curves, not only one scalar score.

## 23. Evaluation follows original episodes

About 75 seconds. Episodes 1–3 train, episode 4 validates, episode 5 tests. All variants inherit their parent split. Overlapping windows from a single trajectory are strongly related, so random row splitting can give optimistic scores. Do not tune the model repeatedly on episode 5. Five parent motions are a small teaching dataset, and one similar-motion test episode cannot establish broad generalization.

## 24. More structure does not guarantee lower error

About 75 seconds. Read the measured reference results: mean 0.5409, ridge 0.1330, direct MLP 0.0865, latent translation 0.0993 nominal N. Lower is better. The direct MLP is better on the combined metric here. Latent translation is still valuable for learning and inspecting representations, but it is not a mandatory accuracy upgrade. Both approaches use the same history inputs, split and evaluation target. The latent pipeline also learns to reconstruct full windows, so this is a practical pipeline comparison, not an isolated test of bottleneck size.

## 25. Your experiments

About 60 seconds. A: compare ridge and the direct MLP, then use one versus seven frames. B: train the autoencoders and compare sensor latent dimension 2, 4 and 8. C: train the translator and compare its prediction with direct regression. Keep other settings fixed and inspect validation results. Record reconstruction error and prediction error separately. The reference measured test result is already shown, so the classroom exercise should not be presented as a new blind benchmark.

## 26. Can simulation predict what ID3 feels?

About 40 seconds. Students should submit one measured-versus-predicted curve, one latent plot and a controlled parameter comparison. Ask them to identify the input and target, explain why they used a bottleneck, distinguish reconstruction from translation, and name information the model cannot know. A useful result includes explaining when the simpler model is sufficient.

## Evidence and implementation

- [Models](../models.py): MLP layers, tanh activations, autoencoders, frozen endpoints and translation objective.
- [Training](../train.py) and [data preparation](../data.py): standardization, optimization and grouped evaluation.
- [Reference metrics](../reference_metrics.json) and [reference results](../REFERENCE_RESULTS.md): measured episode 5 comparisons.
- Raw curves and latent examples are embedded in the HTML. Toy neuron weights, compact-curve parameters and coordinate diagrams are conceptual illustrations.
- Self-reconstruction can use each modality on its own; supervised cross-modal translation needs paired observations. A latent representation is not a guarantee of denoising, interpretability or better prediction.
