from typing import Any, Dict, Tuple

import torch
from lightning import LightningModule
from torchmetrics import MaxMetric, MeanMetric
from torchmetrics.classification import F1Score, Precision, Recall, Specificity
from torchmetrics.classification.accuracy import Accuracy


class ModelModule(LightningModule):
    """Example of a `LightningModule` for MNIST classification.

    A `LightningModule` implements 8 key methods:

    ```python
    def __init__(self):
    # Define initialization code here.

    def setup(self, stage):
    # Things to setup before each stage, 'fit', 'validate', 'test', 'predict'.
    # This hook is called on every process when using DDP.

    def training_step(self, batch, batch_idx):
    # The complete training step.

    def validation_step(self, batch, batch_idx):
    # The complete validation step.

    def test_step(self, batch, batch_idx):
    # The complete test step.

    def predict_step(self, batch, batch_idx):
    # The complete predict step.

    def configure_optimizers(self):
    # Define and configure optimizers and LR schedulers.
    ```

    Docs:
        https://lightning.ai/docs/pytorch/latest/common/lightning_module.html
    """

    def __init__(
        self,
        net: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler,
        compile: bool,
    ) -> None:
        """Initialize a `MNISTLitModule`.

        :param net: The model to train.
        :param optimizer: The optimizer to use for training.
        :param scheduler: The learning rate scheduler to use for training.
        """
        super().__init__()

        # this line allows to access init params with 'self.hparams' attribute
        # also ensures init params will be stored in ckpt
        self.save_hyperparameters(logger=False)

        self.net = net

        # loss function
        self.criterion = torch.nn.BCEWithLogitsLoss() 

        # metric objects for calculating and averaging accuracy across batches
        self.train_acc = Accuracy(task="binary", threshold=0.5)
        self.val_acc = Accuracy(task="binary", threshold=0.5)
        self.test_acc = Accuracy(task="binary", threshold=0.5)

        # for averaging loss across batches
        self.train_loss = MeanMetric()
        self.val_loss = MeanMetric()
        self.test_loss = MeanMetric()

        # for tracking best so far validation accuracy
        self.val_acc_best = MaxMetric()

        # for precision, recall (sensitivity), specificity metric
        self.train_precision = Precision(task="binary", threshold=0.5)
        self.train_sensitivity = Recall(task="binary", threshold=0.5)
        self.train_specificity = Specificity(task="binary", threshold=0.5)
        self.train_f1 = F1Score(task="binary", threshold=0.5)

        self.val_precision = Precision(task="binary", threshold=0.5)
        self.val_sensitivity = Recall(task="binary", threshold=0.5)
        self.val_specificity = Specificity(task="binary", threshold=0.5)
        self.val_f1   = F1Score(task="binary", threshold=0.5)

        self.test_precision = Precision(task="binary", threshold=0.5)
        self.test_sensitivity = Recall(task="binary", threshold=0.5)
        self.test_specificity = Specificity(task="binary", threshold=0.5)
        self.test_f1  = F1Score(task="binary", threshold=0.5)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Perform a forward pass through the model `self.net`.

        :param x: A tensor of images.
        :return: A tensor of logits.
        """
        return self.net(x)

    def on_train_start(self) -> None:
        """Lightning hook that is called when training begins."""
        # by default lightning executes validation step sanity checks before training starts,
        # so it's worth to make sure validation metrics don't store results from these checks
        self.val_loss.reset()
        self.val_acc.reset()
        self.val_acc_best.reset()

    def model_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Perform a single model step on a batch of data.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target labels.

        :return: A tuple containing (in order):
            - A tensor of losses.
            - A tensor of predictions.
            - A tensor of target labels.
        """
        x, y = batch
        logits = self.forward(x)
        logits, y = self.prepare_for_bce_loss(logits, y)
        loss = self.criterion(logits, y)
        probs = torch.sigmoid(logits)
        preds = (probs >= 0.5).int().view(-1)   # shape (B,)
        return loss, preds, y
    
    def on_train_epoch_start(self) -> None:
        self.train_loss.reset()
        self.train_acc.reset()
        self.train_precision.reset()
        self.train_sensitivity.reset()
        self.train_specificity.reset()
        self.train_f1.reset()

    def training_step(
        self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int
    ) -> torch.Tensor:
        """Perform a single training step on a batch of data from the training set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        :return: A tensor of losses between model predictions and targets.
        """
        loss, preds, targets = self.model_step(batch)

        # update and log metrics
        self.train_loss(loss)
        self.train_acc(preds, targets)
        self.train_precision(preds, targets)
        self.train_sensitivity(preds, targets)
        self.train_specificity(preds, targets)
        self.train_f1(preds, targets)
        self.log("train/loss", self.train_loss, on_step=False, on_epoch=True, prog_bar=True)
        self.log("train/acc", self.train_acc, on_step=False, on_epoch=True, prog_bar=True)
        self.log("train/precision", self.train_precision, on_step=False, on_epoch=True, prog_bar=True)
        self.log("train/sensitivity", self.train_sensitivity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("train/specificity", self.train_specificity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("train/f1", self.train_f1, on_step=False, on_epoch=True, prog_bar=True)

        # return loss or backpropagation will fail
        return loss

    def on_train_epoch_end(self) -> None:
        "Lightning hook that is called when a training epoch ends."
        self.print(
            f"Epoch {self.current_epoch}: "
            f"Train Loss: {self.train_loss.compute():.3f}, "
            f"Train Acc: {self.train_acc.compute():.3f}, "
            f"Train Precision: {self.train_precision.compute():.3f}, "
            f"Train Sensitivity: {self.train_sensitivity.compute():.3f}, "
            f"Train Specificity: {self.train_specificity.compute():.3f}, "
            f"Train F1: {self.train_f1.compute():.3f}, "
        )
    
    def on_validation_epoch_start(self) -> None:
        self.val_loss.reset()
        self.val_acc.reset()
        self.val_precision.reset()
        self.val_sensitivity.reset()
        self.val_specificity.reset()
        self.val_f1.reset()


    def validation_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single validation step on a batch of data from the validation set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, preds, targets = self.model_step(batch)

        # update and log metrics
        self.val_loss(loss)
        self.val_acc(preds, targets)
        self.val_precision(preds, targets)
        self.val_sensitivity(preds, targets)
        self.val_specificity(preds, targets)
        self.val_f1(preds, targets)
        self.log("val/loss", self.val_loss, on_step=False, on_epoch=True, prog_bar=True)
        self.log("val/acc", self.val_acc, on_step=False, on_epoch=True, prog_bar=True)
        self.log("val/precision", self.val_precision, on_step=False, on_epoch=True, prog_bar=True)
        self.log("val/sensitivity", self.val_sensitivity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("val/specificity", self.val_specificity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("val/f1", self.val_f1, on_step=False, on_epoch=True, prog_bar=True)

    def on_validation_epoch_end(self) -> None:
        "Lightning hook that is called when a validation epoch ends."
        acc = self.val_acc.compute()  # get current val acc
        self.val_acc_best(acc)  # update best so far val acc
        # log `val_acc_best` as a value through `.compute()` method, instead of as a metric object
        # otherwise metric would be reset by lightning after each epoch
        self.log("val/acc_best", self.val_acc_best.compute(), sync_dist=True, prog_bar=True)
        self.print(
            f"Epoch {self.current_epoch}: "
            f"Val Loss: {self.val_loss.compute():.3f}, "
            f"Val Acc: {self.val_acc.compute():.3f}, "
            f"Val Precision: {self.val_precision.compute():.3f}, "
            f"Val Sensitivity: {self.val_sensitivity.compute():.3f}, "
            f"Val Specificity: {self.val_specificity.compute():.3f}, "
            f"Val F1: {self.val_f1.compute():.3f}, "
        )
    
    def on_test_epoch_start(self) -> None:
        self.test_loss.reset()
        self.test_acc.reset()
        self.test_precision.reset()
        self.test_sensitivity.reset()
        self.test_specificity.reset()
        self.test_f1.reset()

    def test_step(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> None:
        """Perform a single test step on a batch of data from the test set.

        :param batch: A batch of data (a tuple) containing the input tensor of images and target
            labels.
        :param batch_idx: The index of the current batch.
        """
        loss, preds, targets = self.model_step(batch)

        # update and log metrics
        self.test_loss(loss)
        self.test_acc(preds, targets)
        self.test_precision(preds, targets)
        self.test_sensitivity(preds, targets)
        self.test_specificity(preds, targets)
        self.test_f1(preds, targets)
        self.log("test/loss", self.test_loss, on_step=False, on_epoch=True, prog_bar=True)
        self.log("test/acc", self.test_acc, on_step=False, on_epoch=True, prog_bar=True)
        self.log("test/precision", self.test_precision, on_step=False, on_epoch=True, prog_bar=True)
        self.log("test/sensitivity", self.test_sensitivity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("test/specificity", self.test_specificity, on_step=False, on_epoch=True, prog_bar=True)
        self.log("test/f1", self.test_f1, on_step=False, on_epoch=True, prog_bar=True)

    def on_test_epoch_end(self) -> None:
        """Lightning hook that is called when a test epoch ends."""
        self.print(
            f"Epoch {self.current_epoch}: "
            f"Test Loss: {self.test_loss.compute():.3f}, "
            f"Test Acc: {self.test_acc.compute():.3f}, "
            f"Test Precision: {self.test_precision.compute():.3f}, "
            f"Test Sensitivity: {self.test_sensitivity.compute():.3f}, "
            f"Test Specificity: {self.test_specificity.compute():.3f}, "
            f"Test F1: {self.test_f1.compute():.3f}, "
        )

    def setup(self, stage: str) -> None:
        """Lightning hook that is called at the beginning of fit (train + validate), validate,
        test, or predict.

        This is a good hook when you need to build models dynamically or adjust something about
        them. This hook is called on every process when using DDP.

        :param stage: Either `"fit"`, `"validate"`, `"test"`, or `"predict"`.
        """
        if self.hparams.compile and stage == "fit":
            self.net = torch.compile(self.net)

    def configure_optimizers(self) -> Dict[str, Any]:
        """Choose what optimizers and learning-rate schedulers to use in your optimization.
        Normally you'd need one. But in the case of GANs or similar you might have multiple.

        Examples:
            https://lightning.ai/docs/pytorch/latest/common/lightning_module.html#configure-optimizers

        :return: A dict containing the configured optimizers and learning-rate schedulers to be used for training.
        """
        optimizer = self.hparams.optimizer(params=self.trainer.model.parameters())
        if self.hparams.scheduler is not None:
            scheduler = self.hparams.scheduler(optimizer=optimizer)
            return {
                "optimizer": optimizer,
                "lr_scheduler": {
                    "scheduler": scheduler,
                    "monitor": "val/loss",
                    "interval": "epoch",
                    "frequency": 1,
                },
            }
        return {"optimizer": optimizer}

    def prepare_for_bce_loss(self, preds, targets):
        """
        Prepares prediction and target tensors for use with BCEWithLogitsLoss or BCELoss.
        Ensures matching shapes and correct types.
        """
        # Convert targets to float (required for BCE loss)
        targets = targets.float()

        # Flatten predictions if they have extra trailing dimensions
        if preds.ndim > 1 and preds.shape[1] == 1:
            preds = preds.view(-1)
        
        # Flatten targets similarly
        if targets.ndim > 1 and targets.shape[1] == 1:
            targets = targets.view(-1)

        # If preds and targets don't match shape, try to align
        if preds.shape != targets.shape:
            try:
                preds = preds.view(-1)
                targets = targets.view(-1)
            except Exception as e:
                raise ValueError(f"Could not align preds and targets shapes: {e}")

        return preds, targets