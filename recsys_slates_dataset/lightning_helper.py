# AUTOGENERATED! DO NOT EDIT! File to edit: lightning_helper.ipynb (unless otherwise specified).

__all__ = ['SlateDataModule', 'CallbackPrintRecommendedCategory', 'Hitrate']

# Cell
import recsys_slates_dataset.dataset_torch as dataset_torch
import recsys_slates_dataset.data_helper as data_helper
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
        sample_candidate_items=0,
        valid_pct= 0.05,
        test_pct= 0.05,
        t_testsplit= 5,
        limit_num_users=None,
        *args, **kwargs):

        super().__init__()
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.num_workers =num_workers
        self.sample_candidate_items=sample_candidate_items
        self.valid_pct=valid_pct
        self.test_pct=test_pct
        self.t_testsplit=t_testsplit
        self.limit_num_users = limit_num_users
    def prepare_data(self):
        """
        Download data to disk if not already downloaded.
        """
        data_helper.download_data_files(data_dir=self.data_dir)

    def setup(self, stage=None, num_negative_queries=0):

        logging.info('Load data..')
        self.ind2val, self.attributes, self.dataloaders = dataset_torch.load_dataloaders(
            data_dir= self.data_dir,
            batch_size=self.batch_size,
            num_workers= self.num_workers,
            sample_candidate_items=self.sample_candidate_items,
            valid_pct= self.valid_pct,
            test_pct= self.test_pct,
            t_testsplit= self.t_testsplit,
            limit_num_users=self.limit_num_users)


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

# Cell
import numpy as np
import torch
class CallbackPrintRecommendedCategory(pl.Callback):
    """ A pytorch lightning callback that prints the clicks the user did, and the top recommendations at a given interaction."""
    def __init__(self, dm, num_recs=2, max_interactions=10, report_interval=100):
        self.dm = dm
        self.num_recs= num_recs
        self.max_interactions=max_interactions
        self.report_interval = report_interval

        # Extract some data and index to report:
        self.batch = next(iter(self.dm.train_dataloader())) # batch of data to visualize
        self.idx = 12


    @torch.no_grad()
    def on_validation_epoch_end(self, trainer, pl_module):
        if trainer.current_epoch % self.report_interval==0:
            for idx in [self.idx+k for k in range(5)]:
                smallbatch = {key: val[idx].detach().clone().unsqueeze(0).to(pl_module.device).long() for key, val in self.batch.items()}

                # Build recommendations for items:
                M = torch.zeros(self.num_recs+1, self.max_interactions)
                M[0,:] = smallbatch['click'].flatten()[:self.max_interactions] # add view to first row
                for t_rec in range(self.max_interactions):
                    scores = pl_module.forward(smallbatch, t_rec=t_rec)
                    vals, rec_ids = scores.topk(self.num_recs)
                    M[1:, t_rec] = rec_ids

                def itemidx2string(itemidx):
                    cat_idx = self.dm.attributes['category'][itemidx]
                    s = self.dm.ind2val['category'][cat_idx]
                    return s

                title_mat = np.vectorize(itemidx2string)(M.long().numpy())

                # compute the other elements:
                slate_type = [self.dm.ind2val['interaction_type'][int(idx)] for idx in smallbatch['interaction_type'].flatten()]
                row_tbl = lambda title,elements: f'| **{title}**   | {" | ".join(elements[:self.max_interactions])} | '

                table = []
                table.append(f'| interaction step  | {" | ".join([f"t={i}" for i in range(self.max_interactions)])} | ')
                table.append(f'| -------           | {"-------|"*(self.max_interactions)}')
                table.append( row_tbl("slate type"   , slate_type) )
                table.append( row_tbl("Clicks", title_mat[0]) )
                table.append(f'| -------           | {"-------|"*(self.max_interactions)}')
                for k, elements in enumerate(title_mat[1:]):
                    table.append( row_tbl(f"rec item {k}", elements) )

                trainer.logger.experiment.add_text(f"user_{idx}", "\n ".join(table), global_step=trainer.global_step)


# Cell
from tqdm import tqdm
import numpy as np
class Hitrate(pl.Callback):
    """ Module computing hitrate over the test dataset.
    NB: This assumes that recommendations does not change over time.
    I.e. will not work on temporal models.
    """
    def __init__(self,dm, report_interval=100, num_rec=10, remove_already_clicked=True):
        self.dm=dm
        self.report_interval = report_interval
        self.num_rec = num_rec
        self.remove_already_clicked = remove_already_clicked

    @torch.no_grad()
    def calc_hits_in_batch(self, batch, pl_module):
        # Move batch data to model device:
        batch = {key: val.to(pl_module.device) for key, val in batch.items()}

        batch_recs = pl_module.recommend_batch(batch,num_rec= self.num_rec,t_rec=-1).detach().cpu()

        # If a recommendation already appears in the training click sequence, remove it from recommendations.
        # It is removed by setting the recommendation to a negative number ( :rolling_eyes:, i know),
        # which will not be counted. This makes it faster&paralleizeable in the np.intersect1d part.
        if self.remove_already_clicked:
            dont_count_clicks = (batch['click']*(~batch['phase_mask'])).detach().cpu()
            for n in range(batch_recs.size(1)):
                rec_clicked_item = (batch_recs[:,n].unsqueeze(1)==dont_count_clicks).max(dim=1)[0]
                batch_recs[rec_clicked_item,n] = -1

        positive_clicks = (batch['click']*batch['phase_mask']).detach().cpu()

        hits_in_batch = 0
        for k in range(len(batch_recs)):
            hits_in_batch += len(np.intersect1d(positive_clicks[k,], batch_recs[k,]))

        num_users = batch_recs.size(0)
        return hits_in_batch, num_users

    @torch.no_grad()
    def calc_hitrate(self, pl_module):
        test_dataloader = self.dm.test_dataloader()
        hits, users = 0,0
        pbar = tqdm(test_dataloader, total=len(test_dataloader))
        for batch in pbar:
            pbar.set_description(f"Hitrate Calc, hits/users: {hits}/{users}")
            hits_in_batch, num_users_batch = self.calc_hits_in_batch(batch, pl_module)
            hits += hits_in_batch
            users += num_users_batch

        hitrate = hits/users
        return hitrate
    def on_train_epoch_end(self, trainer, pl_module):
        if trainer.current_epoch % self.report_interval==0:
            hitrate = self.calc_hitrate(pl_module)
            trainer.logger.experiment.add_scalar(f'test/hitrate_{self.num_rec}', hitrate, global_step=trainer.global_step)