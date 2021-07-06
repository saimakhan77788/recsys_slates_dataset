# AUTOGENERATED! DO NOT EDIT! File to edit: lightninghelper.ipynb (unless otherwise specified).

__all__ = ['SlateDataModule']

# Cell
import recsys_slates_dataset.dataset_torch as dataset_torch
import recsys_slates_dataset.datahelper as datahelper
import pytorch_lightning as pl
import logging
class SlateDataModule(pl.LightningDataModule):
    """
    A LightningDataModule wrapper around the dataloaders created in dataset_torch.
    """
    def __init__(
        self,
        data_dir= "dat",
        batch_size=1024,
        num_workers= 0,
        sample_uniform_slate=False,
        valid_pct= 0.05,
        test_pct= 0.05,
        t_testsplit= 5, *args, **kwargs):

        super().__init__()
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.num_workers =num_workers
        self.sample_uniform_slate=sample_uniform_slate
        self.valid_pct=valid_pct
        self.test_pct=test_pct
        self.t_testsplit=t_testsplit
    def prepare_data(self):
        """
        Download data to disk if not already downloaded.
        """
        datahelper.download_data_files(data_dir=self.data_dir)

    def setup(self, stage=None, num_negative_queries=0):

        logging.info('Load data..')
        self.ind2val, self.attributes, self.dataloaders = dataset_torch.load_dataloaders(
            data_dir= self.data_dir,
            batch_size=self.batch_size,
            num_workers= self.num_workers,
            sample_uniform_slate=self.sample_uniform_slate,
            valid_pct= self.valid_pct,
            test_pct= self.test_pct,
            t_testsplit= self.t_testsplit)


        # Add some descriptive stats to the dataset as variables for easy access later:
        self.num_items = self.train_dataloader().dataset.data['slate'].max().item()+1
        _ , self.num_interactions, self.maxlen_slate = self.train_dataloader().dataset.data['slate'].size()
        self.num_users = self.train_dataloader().dataset.data['userId'].max().item()+1
        self.num_interaction_types = len(self.ind2val['interaction_type'])

    def train_dataloader(self):
        return self.dataloaders["train"]

    def val_dataloader(self):
        return self.dataloaders["valid"]

    def test_dataloader(self):
        return self.dataloaders["test"]