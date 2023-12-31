import cv2
import os
import torch 
from torch import nn as nn
from torch.nn import functional as F
import matplotlib.pyplot as plt

torch.manual_seed(2000)

batch_size = 50 # 20 # 16
image_folders = os.listdir("Dataset/Images")
device = "cuda" if torch.cuda.is_available else "cpu"
print(f"Device: {device}")
image_size = (100, 100)
n_colour_channels = 3 # (R, G, B)
num_image_pixels = image_size[0] * image_size[1] * n_colour_channels

# Splits and distributions for generating batches
num_types = len(image_folders)
uniform_types_distribution = torch.ones(num_types, dtype = torch.float32, device = device) / num_types # 5 types of rice

# 5 types of rice, 15000 images for each = 75000 total
# 75000 * 0.1 = 7500 images in total for test/validation split
# 7500 / 5 = 1500 images of each type for test/validation split
test_split_multiplier = 0.1
val_split_multiplier = 0.1

num_test_imgs = int((75000 * test_split_multiplier) / 5)
num_val_imgs = int((75000 * val_split_multiplier) / 5)
num_train_imgs = int(15000 - num_test_imgs - num_val_imgs)
print(num_train_imgs, num_val_imgs, num_test_imgs)

uniform_train_images_distribution = torch.ones(num_train_imgs, dtype = torch.float32, device = device) / num_train_imgs # 15000 images for each type of rice
uniform_test_images_distribution = torch.ones(num_test_imgs, dtype = torch.float32, device = device) / num_test_imgs
uniform_val_images_distribution = torch.ones(num_val_imgs, dtype = torch.float32, device = device) / num_val_imgs

# print(uniform_train_images_distribution.dtype)
# print(uniform_types_distribution.dtype)
# print(uniform_types_distribution)
# print(uniform_train_images_distribution)

def img_to_matrix(image_indexes, r_type_indexes, img_size, img_num_pixels):

    # Creates all pixel matrixes in a batch

    # Find all rice types in the selected batch
    rice_types = [image_folders[r_type_i] for r_type_i in r_type_indexes]

    # print(rice_types)
    # print(image_indexes)
    
    matrices = []

    for img_type, img_num in zip(rice_types, image_indexes):

        # img_num.item() as img_num is a tensor containing the image number
        img_path = f"Dataset/Images/{img_type}/{img_type} ({str(img_num.item())}).jpg" # E.g. Dataset/Images/Jasmine/Jasmine (3).jpg"

        # Read image into numpy array
        img_np = cv2.imread(img_path)

        # Scale down image
        img_np = cv2.resize(img_np, img_size)

        # Create PyTorch tensor from numpy array
        img_pt = torch.from_numpy(img_np).float()

        # Add to matrices list
        matrices.append(img_pt.view(img_num_pixels))

        # Release image memory
        del img_np, img_pt

    # Add all the matrices into a single tensor [Shape: (batch_size, pixel_number)]
    matrices = torch.stack(matrices, dim = 0)
    
    return matrices
    
def generate_batch(batch_size, split):
    
    # Generate indexes for rice types
    rice_type_indexes = torch.multinomial(input = uniform_types_distribution, num_samples = batch_size, replacement = True)

    # Convert the index into a one-hot vector for the entire batch
    rice_types = torch.zeros(batch_size, 5, device = device)
    rice_types[torch.arange(batch_size), rice_type_indexes - 1] += 1 # 2nd option = index 1 (Possible indexes = 0, 1, 2, 3, 4 ... num_types)
    
    # -------------------------------
    # Train split images
    if split == "Train":
        # Generate indexes for rice images
        rice_image_indexes = torch.multinomial(input = uniform_train_images_distribution, num_samples = batch_size, replacement = True)
        rice_image_indexes += 1 # The indexes only go from 0 - 14999 but the numbers at the end of each image go from 1 - 15000
    
    # Val split images
    elif split == "Val":
        # Generate indexes for rice images
        rice_image_indexes = torch.multinomial(input = uniform_val_images_distribution, num_samples = batch_size, replacement = True)
        # Note: If val_split_multiplier = 0.1: 15000 - 1500 - 1500 + 1 = 12001 
        # i.e. images at indexes 12001 - 13500 for each rice type are for the val split
        rice_image_indexes += (15000 - num_test_imgs - num_val_imgs) + 1 # The indexes only go from 0 - 14999 but the numbers at the end of each image go from 1 - 15000
    
    # Test split images
    else:
        # Note: uniform_test_images_distribution will have a smaller range of index values 
        # - (e.g. if num_test_imgs = 7500, as there are 5 types, the last (7500 / 5) = 1500 images of this type are for the test split)
        # - i.e. Only images at indexes 13501 - 15000 will be used for the test split
        rice_image_indexes = torch.multinomial(input = uniform_test_images_distribution, num_samples = batch_size, replacement = True)
        rice_image_indexes += (15000 - num_test_imgs) + 1 # The indexes only go from 0 - 14999 but the numbers at the end of each image go from 1 - 15000
    
    # Convert indexes to matrices
    rice_image_matrices = img_to_matrix(image_indexes = rice_image_indexes, r_type_indexes = rice_type_indexes, img_size = image_size, img_num_pixels = num_image_pixels)

    # Pixel matrices, Labels
    return rice_image_matrices.to(device = device), rice_types.to(device = device)
        
@torch.no_grad()
def split_loss(split):
    
    X, Y = generate_batch(batch_size = batch_size, split = split)

    # Forward pass
    logits = model(X) # (batch_size, 5)

    # Cross-entropy loss
    loss = F.cross_entropy(logits, Y)

    print(f"{split}Loss: {loss.item()}")

@torch.no_grad()
def evaluate_loss(num_iterations):
    
    model.eval()

    # Holds the losses for the train split and val split (with no change in model parameters)
    split_losses = {}

    for split in ("Train", "Val"):

        losses = torch.zeros(num_iterations, device = device)
        accuracies = torch.zeros(num_iterations, device = device)

        for x in range(num_iterations):
            Xev, Yev = generate_batch(batch_size = batch_size, split = split)

            # Forward pass
            logits = model(Xev)
            # Cross-Entropy loss
            loss = F.cross_entropy(logits, Yev)
            # Set loss
            losses[x] = loss.item()

            # Val accuracy
            if split == "Val":
                # Find the accuracy on the predictions on this batch
                accuracies[x] = (count_correct_preds(predictions = logits, targets = Yev).item() / batch_size) * 100 # Returns tensor containing the number of correct predictions
                # print(f"Accuracy on batch: {accuracies[x]}")

        split_losses[split] = losses.mean()
        avg_val_accuracy = accuracies.mean()
    
    model.train() 

    return split_losses, avg_val_accuracy

def count_correct_preds(predictions, targets):
    # Find the predictions of the model
    _, output = torch.max(predictions, dim = 1) 
    output = F.one_hot(output, num_classes = 5) # 5 types of rice

    # Return the number of correct predictions
    return torch.sum((output == targets).all(axis = 1))

# No.of inputs = Number of pixels in image 
model = nn.Sequential(

                    # # 1
                    # nn.Linear(10000, 5000),
                    # nn.BatchNorm1d(num_features = 5000),
                    # nn.ReLU(),

                    # nn.Linear(5000, 2500),
                    # nn.BatchNorm1d(num_features = 2500),
                    # nn.ReLU(),

                    # nn.Linear(2500, 5),

                    # # 2
                    # nn.Linear(10000, 2500),
                    # nn.BatchNorm1d(num_features = 2500),
                    # nn.ReLU(),

                    # nn.Linear(2500, 5)

                    # # 3
                    # nn.Linear(10000, 7500),
                    # nn.BatchNorm1d(num_features = 7500),
                    # nn.ReLU(),

                    # nn.Linear(7500, 5000),
                    # nn.BatchNorm1d(num_features = 5000),
                    # nn.ReLU(),

                    # nn.Linear(5000, 2500),
                    # nn.BatchNorm1d(num_features = 2500),
                    # nn.ReLU(),

                    # nn.Linear(2500, 1250),
                    # nn.BatchNorm1d(num_features = 1250),
                    # nn.ReLU(),

                    # nn.Linear(1250, 625),
                    # nn.BatchNorm1d(num_features = 625),
                    # nn.ReLU(),

                    # nn.Linear(625, 5)

                    # # 4 (125 x 125) image size
                    # nn.Linear(num_image_pixels, 10000),
                    # nn.BatchNorm1d(num_features = 10000),
                    # nn.ReLU(),

                    # nn.Linear(10000, 7500),
                    # nn.BatchNorm1d(num_features = 7500),
                    # nn.ReLU(),

                    # nn.Linear(7500, 5000),
                    # nn.BatchNorm1d(num_features = 5000),
                    # nn.ReLU(),

                    # nn.Linear(5000, 2500),
                    # nn.BatchNorm1d(num_features = 2500),
                    # nn.ReLU(),

                    # nn.Linear(2500, 1250),
                    # nn.BatchNorm1d(num_features = 1250),
                    # nn.ReLU(),

                    # nn.Linear(1250, 625),
                    # nn.BatchNorm1d(num_features = 625),
                    # nn.ReLU(),

                    # nn.Linear(625, 5)

                    # 5 (Adapted set-up 3 to work with 3 colour channels) [Cannot add nn.Linear(30000, 10000) instead due to OutOfMemory error]
                    nn.Linear(30000, 7500),
                    nn.BatchNorm1d(num_features = 7500),
                    nn.ReLU(),

                    nn.Linear(7500, 5000),
                    nn.BatchNorm1d(num_features = 5000),
                    nn.ReLU(),

                    nn.Linear(5000, 2500),
                    nn.BatchNorm1d(num_features = 2500),
                    nn.ReLU(),

                    nn.Linear(2500, 1250),
                    nn.BatchNorm1d(num_features = 1250),
                    nn.ReLU(),

                    nn.Linear(1250, 625),
                    nn.BatchNorm1d(num_features = 625),
                    nn.ReLU(),

                    nn.Linear(625, 5)

                    )
model.to(device = device)

# Initialisation
with torch.no_grad():

    # Kai-ming initialisation
    for layer in model:
        if isinstance(layer, nn.Linear):
            torch.nn.init.kaiming_normal_(layer.weight, mode = "fan_in", nonlinearity = "relu")
            # print(layer.weight.std(), layer.weight.mean())

            # 2nd method:
            # fan_in = layer.weight.size(1)
            # std = torch.sqrt(torch.tensor(2.0 / fan_in))
            # nn.init.normal(layer.weight, mean = 0, std = std)
            # print(layer.weight.std(), layer.weight.mean())


# Optimisers
# optimiser = torch.optim.SGD(model.parameters(), lr = 0.1) # Stochastic gradient descent
optimiser = torch.optim.AdamW(model.parameters(), lr = 1e-3) # Adam (updates learning rate for each weight individually)

Xtr, Ytr = generate_batch(batch_size = batch_size, split = "Train")
print(Xtr.shape)

losses_i = []
accuracies = []

for i in range(20000):
    
    # Generate batch of images
    Xtr, Ytr = generate_batch(batch_size = batch_size, split = "Train")

    # Forward pass
    logits = model(Xtr) # (batch_size, 5)

    # Cross-entropy loss
    loss = F.cross_entropy(logits, Ytr)
    
    # Set gradients to 0
    optimiser.zero_grad()
    
    # Backward pass
    loss.backward()
    
    # Update model parameters
    optimiser.step()
    
    # -----------------------------------------------
    # Tracking stats:
    losses_i.append(loss.log10().item()) # log10 for better visualisation

    if i % 50 == 0:
        split_losses, val_acc = evaluate_loss(num_iterations = 20)
        print(f"Epoch: {i} | TrainLoss: {split_losses['Train']:.4f} | ValLoss: {split_losses['Val']:.4f} | AverageValAccuracy: {val_acc}%")
        accuracies.append(val_acc)


losses_i = torch.tensor(losses_i).view(-1, 100).mean(1) 
plt.plot(losses_i)
plt.show()

# Evaluate model
model.eval()
split_loss("Train")
split_loss("Val")
split_loss("Test")
print(f"AvgValAccuracy: {sum(accuracies) / len(accuracies)}") # Average val accuracy overall whilst the model was training

test_losses_i = []
num_correct = 0
num_tested = 0
test_steps = 300
test_batch_size = 50
with torch.no_grad():
    
    for i in range(test_steps):
        Xte, Yte = generate_batch(batch_size = test_batch_size, split = "Test")

        logits = model(Xte)
        loss = F.cross_entropy(logits, Yte)

        num_correct += count_correct_preds(predictions = logits, targets = Yte)
        num_tested += test_batch_size
        test_losses_i.append(loss.log10().item())

        if (i + 1) % 50 == 0: # i = 99, this is the 100th iteration
            print(f"Correct predictions: {num_correct} / {num_tested} | Accuracy(%): {(num_correct / num_tested) * 100}")

test_losses_i = torch.tensor(test_losses_i).view(-1, 100).mean(1) 
plt.plot(test_losses_i)
plt.show()

# Tests:

# 3rd set-up for model:

# (20 batch size)
# 20000 steps + Kai-Ming initialised

# TrainLoss: 0.0906727984547615
# ValLoss: 0.37636175751686096
# TestLoss: 0.33868202567100525
# AvgValAccuracy: 86.28437042236328
# Correct predictions: 13581 / 15000 | Accuracy(%): 90.5400009155273

# ----------------------------------
# (50 batch size)
# 20000 steps + Kai-Ming initialised

# TrainLoss: 0.019007110968232155
# ValLoss: 0.618399441242218
# TestLoss: 0.28131961822509766
# AvgValAccuracy: 88.45275115966797
# Correct predictions: 13236 / 15000 | Accuracy(%): 88.24000549316406


# --------------------------------------------------------
# 4th set-up for model: [(125 x 125) image size (was set to (100, 100) for the other tests)]

# (50 batch size)
# 20000 steps + Kai-Ming initialised

# TrainLoss: 0.0330025739967823
# ValLoss: 0.17014716565608978
# TestLoss: 0.6086336374282837
# AvgValAccuracy: 88.6610107421875
# Correct predictions: 13526 / 15000 | Accuracy(%): 90.17333221435547

# --------------------------------------------------------
# 4th set-up for model: [(100, 100) image size]

# (20 batch size) 
# 20000 steps + Kai-Ming initialised

# TrainLoss: 0.004270065575838089
# ValLoss: 0.22270695865154266
# TestLoss: 0.2747001349925995
# AvgValAccuracy: 89.0668716430664
# Correct predictions: 13447 / 15000 | Accuracy(%): 89.64666748046875

# ----------------------------------
# (50 batch size) 
# 20000 steps + Kai-Ming initialised

# TrainLoss: 0.003974916413426399
# ValLoss: 0.07606350630521774
# TestLoss: 0.21054767072200775
# AvgValAccuracy: 92.39400482177734
# Correct predictions: 14403 / 15000 | Accuracy(%): 96.02000427246094