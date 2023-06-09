﻿"""
The :mod:`imblearn.pipeline` module implements utilities to build a
composite estimator, as a chain of transforms, samples and estimators.

Adapted from imblearn.pipeline, which is adapted from sklearn.pipeline.
Authors and the license information of the original module is given below.
Allows modifying "y" in both train and test time which is required in the tasks such as outlier removal.

Currently only tested and supports combining several transformer/resamplers with a regressor,
should work with a classifier, might not work with only transformers/resamplers.

Resamplers should implement the fit_resample() and transform() functions following the signatures:
X, y = fit_resample(X, y=None)
X, y/ind_to_keep = transform(X, y=None)
 - In the case that y is given, it should return y (training time).
 - In the case y is not given, should return the indices of the data points to keep; the points that are not removed.
Score functions should be implemented with the form:
def score_function(estimator, X_test, y_test):
    y_pred = estimator.predict(X_test)
    if len(y_test) != len(y_pred):
        remain_inds = estimator.to_keep_ind
        y_test = [y_test[x] for x in remain_inds]
    score = original_score_function(y_test, y_pred)
    return score
"""

# Author: Edouard Duchesnay
#         Gael Varoquaux
#         Virgile Fritsch
#         Alexandre Gramfort
#         Lars Buitinck
#         Christos Aridas
#         Guillaume Lemaitre <g.lemaitre58@gmail.com>
# License: BSD
from sklearn import pipeline
from sklearn.base import clone
from sklearn.utils import _print_elapsed_time
from sklearn.utils.metaestimators import if_delegate_has_method
from sklearn.utils.validation import check_memory

__all__ = ["Pipeline", "make_pipeline"]


class Pipeline(pipeline.Pipeline):
    """Pipeline of transforms and resamples with a final estimator.

    Sequentially apply a list of transforms, sampling, and a final estimator.
    Intermediate steps of the pipeline must be transformers or resamplers,
    that is, they must implement fit, transform and sample methods.
    The samplers are only applied during fit.
    The final estimator only needs to implement fit.
    The transformers and samplers in the pipeline can be cached using
    ``memory`` argument.

    The purpose of the pipeline is to assemble several steps that can be
    cross-validated together while setting different parameters.
    For this, it enables setting parameters of the various steps using their
    names and the parameter name separated by a '__', as in the example below.
    A step's estimator may be replaced entirely by setting the parameter
    with its name to another estimator, or a transformer removed by setting
    it to 'passthrough' or ``None``.

    Parameters
    ----------
    steps : list
        List of (name, transform) tuples (implementing
        fit/transform/fit_resample) that are chained, in the order in which
        they are chained, with the last object an estimator.

    memory : Instance of joblib.Memory or str, default=None
        Used to cache the fitted transformers of the pipeline. By default,
        no caching is performed. If a string is given, it is the path to
        the caching directory. Enabling caching triggers a clone of
        the transformers before fitting. Therefore, the transformer
        instance given to the pipeline cannot be inspected
        directly. Use the attribute ``named_steps`` or ``steps`` to
        inspect estimators within the pipeline. Caching the
        transformers is advantageous when fitting is time consuming.

    verbose : bool, default=False
        If True, the time elapsed while fitting each step will be printed as it
        is completed.

    Attributes
    ----------
    named_steps : bunch object, a dictionary with attribute access
        Read-only attribute to access any step parameter by user given name.
        Keys are step names and values are steps parameters.

    See Also
    --------
    make_pipeline : Helper function to make pipeline.

    Notes
    -----
    See :ref:`sphx_glr_auto_examples_pipeline_plot_pipeline_classification.py`

    Examples
    --------
    >>> from collections import Counter
    >>> from sklearn.datasets import make_classification
    >>> from sklearn.model_selection import train_test_split as tts
    >>> from sklearn.decomposition import PCA
    >>> from sklearn.neighbors import KNeighborsClassifier as KNN
    >>> from sklearn.metrics import classification_report
    >>> from imblearn.over_sampling import SMOTE
    >>> from imblearn.pipeline import Pipeline # doctest: +NORMALIZE_WHITESPACE
    >>> X, y = make_classification(n_classes=2, class_sep=2,
    ... weights=[0.1, 0.9], n_informative=3, n_redundant=1, flip_y=0,
    ... n_features=20, n_clusters_per_class=1, n_samples=1000, random_state=10)
    >>> print('Original dataset shape {}'.format(Counter(y)))
    Original dataset shape Counter({1: 900, 0: 100})
    >>> pca = PCA()
    >>> smt = SMOTE(random_state=42)
    >>> knn = KNN()
    >>> pipeline = Pipeline([('smt', smt), ('pca', pca), ('knn', knn)])
    >>> X_train, X_test, y_train, y_test = tts(X, y, random_state=42)
    >>> pipeline.fit(X_train, y_train) # doctest: +ELLIPSIS
    Pipeline(...)
    >>> y_hat = pipeline.predict(X_test)
    >>> print(classification_report(y_test, y_hat))
                  precision    recall  f1-score   support
    <BLANKLINE>
               0       0.87      1.00      0.93        26
               1       1.00      0.98      0.99       224
    <BLANKLINE>
        accuracy                           0.98       250
       macro avg       0.93      0.99      0.96       250
    weighted avg       0.99      0.98      0.98       250
    <BLANKLINE>
    """

    # BaseEstimator interface

    def _validate_steps(self):
        names, estimators = zip(*self.steps)

        # validate names
        self._validate_names(names)

        # validate estimators
        transformers = estimators[:-1]
        estimator = estimators[-1]

        for t in transformers:
            # if t is None or t == "passthrough":
            #     continue
            # if not (
            #     hasattr(t, "fit")
            #     or hasattr(t, "fit_transform")
            #     or hasattr(t, "fit_resample")
            # ) or not (hasattr(t, "transform") or hasattr(t, "fit_resample")):
            #     raise TypeError(
            #         "All intermediate steps of the chain should "
            #         "be estimators that implement fit and transform or "
            #         "fit_resample (but not both) or be a string 'passthrough' "
            #         "'%s' (type %s) doesn't)" % (t, type(t))
            #     )
            # if hasattr(t, "fit_resample") and (
            #     hasattr(t, "fit_transform") or hasattr(t, "transform")
            # ):
            #     raise TypeError(
            #         "All intermediate steps of the chain should "
            #         "be estimators that implement fit and transform or "
            #         "fit_resample."
            #         " '%s' implements both)" % (t)
            #     )
            if t is None or t == "passthrough":
                continue
            if not (
                hasattr(t, "fit")
                or hasattr(t, "fit_transform")
                or hasattr(t, "fit_resample")
            ) or not (hasattr(t, "transform") or hasattr(t, "fit_resample")):
                raise TypeError(
                    "All intermediate steps of the chain should "
                    "be estimators that implement fit and transform or "
                    "fit_resample (but not both) or be a string 'passthrough' "
                    "'%s' (type %s) doesn't)" % (t, type(t))
                )
            if isinstance(t, pipeline.Pipeline):
                raise TypeError(
                    "All intermediate steps of the chain should not be"
                    " Pipelines"
                )

        # We allow last estimator to be None as an identity transformation
        if (
            estimator is not None
            and estimator != "passthrough"
            and not hasattr(estimator, "fit")
        ):
            raise TypeError(
                "Last step of Pipeline should implement fit or be "
                "the string 'passthrough'. '%s' (type %s) doesn't"
                % (estimator, type(estimator))
            )

    def _iter(
        self, with_final=True, filter_passthrough=True, filter_resample=True
    ):
        """Generate (idx, (name, trans)) tuples from self.steps.

        When `filter_passthrough` is `True`, 'passthrough' and None
        transformers are filtered out. When `filter_resample` is `True`,
        estimator with a method `fit_resample` are filtered out.
        """
        it = super()._iter(with_final, filter_passthrough)
        if filter_resample:
            return filter(lambda x: not hasattr(x[-1], "fit_resample"), it)
        else:
            return it

    # Estimator interface

    def _fit(self, X, y=None, **fit_params):
        self.steps = list(self.steps)
        self._validate_steps()
        # Setup the memory
        memory = check_memory(self.memory)

        fit_transform_one_cached = memory.cache(pipeline._fit_transform_one)
        fit_resample_one_cached = memory.cache(_fit_resample_one)

        fit_params_steps = {
            name: {} for name, step in self.steps if step is not None
        }
        for pname, pval in fit_params.items():
            if '__' not in pname:
                raise ValueError(
                    "Pipeline.fit does not accept the {} parameter. "
                    "You can pass parameters to specific steps of your "
                    "pipeline using the stepname__parameter format, e.g. "
                    "`Pipeline.fit(X, y, logisticregression__sample_weight"
                    "=sample_weight)`.".format(pname))
            step, param = pname.split("__", 1)
            fit_params_steps[step][param] = pval
        for (step_idx,
             name,
             transformer) in self._iter(with_final=False,
                                        filter_passthrough=False,
                                        filter_resample=False):
            if transformer is None or transformer == 'passthrough':
                with _print_elapsed_time('Pipeline',
                                         self._log_message(step_idx)):
                    continue

            try:
                # joblib >= 0.12
                mem = memory.location
            except AttributeError:
                mem = memory.cachedir
            finally:
                cloned_transformer = clone(transformer) if mem else transformer

            # Fit or load from cache the current transfomer
            if (hasattr(cloned_transformer, "transform") or hasattr(
                cloned_transformer, "fit_transform"
            )) and not hasattr(cloned_transformer, "fit_resample"):
                X, fitted_transformer = fit_transform_one_cached(
                    cloned_transformer, X, y, None,
                    message_clsname='Pipeline',
                    message=self._log_message(step_idx),
                    **fit_params_steps[name]
                )
            elif hasattr(cloned_transformer, "fit_resample"):
                X, y, fitted_transformer = fit_resample_one_cached(
                    cloned_transformer, X, y,
                    message_clsname='Pipeline',
                    message=self._log_message(step_idx),
                    **fit_params_steps[name]
                )
            # Replace the transformer of the step with the fitted
            # transformer. This is necessary when loading the transformer
            # from the cache.
            self.steps[step_idx] = (name, fitted_transformer)
        if self._final_estimator == "passthrough":
            return X, y, {}
        return X, y, fit_params_steps[self.steps[-1][0]]

    def fit(self, X, y=None, **fit_params):
        """Fit the model.

        Fit all the transforms/samplers one after the other and
        transform/sample the data, then fit the transformed/sampled
        data using the final estimator.

        Parameters
        ----------
        X : iterable
            Training data. Must fulfill input requirements of first step of the
            pipeline.

        y : iterable, default=None
            Training targets. Must fulfill label requirements for all steps of
            the pipeline.

        **fit_params : dict of str -> object
            Parameters passed to the ``fit`` method of each step, where
            each parameter name is prefixed such that parameter ``p`` for step
            ``s`` has key ``s__p``.

        Returns
        -------
        self : Pipeline
            This estimator.
        """
        Xt, yt, fit_params = self._fit(X, y, **fit_params)
        with _print_elapsed_time('Pipeline',
                                 self._log_message(len(self.steps) - 1)):
            if self._final_estimator != "passthrough":
                self._final_estimator.fit(Xt, yt, **fit_params)
        return self

    def fit_transform(self, X, y=None, **fit_params):
        """Fit the model and transform with the final estimator.

        Fits all the transformers/samplers one after the other and
        transform/sample the data, then uses fit_transform on
        transformed data with the final estimator.

        Parameters
        ----------
        X : iterable
            Training data. Must fulfill input requirements of first step of the
            pipeline.

        y : iterable, default=None
            Training targets. Must fulfill label requirements for all steps of
            the pipeline.

        **fit_params : dict of string -> object
            Parameters passed to the ``fit`` method of each step, where
            each parameter name is prefixed such that parameter ``p`` for step
            ``s`` has key ``s__p``.

        Returns
        -------
        Xt : array-like of shape (n_samples, n_transformed_features)
            Transformed samples.
        """
        last_step = self._final_estimator
        Xt, yt, fit_params = self._fit(X, y, **fit_params)
        with _print_elapsed_time('Pipeline',
                                 self._log_message(len(self.steps) - 1)):
            if last_step == "passthrough":
                return Xt
            elif hasattr(last_step, "fit_transform"):
                return last_step.fit_transform(Xt, yt, **fit_params)
            else:
                return last_step.fit(Xt, yt, **fit_params).transform(Xt)

    def fit_resample(self, X, y=None, **fit_params):
        """Fit the model and sample with the final estimator.

        Fits all the transformers/samplers one after the other and
        transform/sample the data, then uses fit_resample on transformed
        data with the final estimator.

        Parameters
        ----------
        X : iterable
            Training data. Must fulfill input requirements of first step of the
            pipeline.

        y : iterable, default=None
            Training targets. Must fulfill label requirements for all steps of
            the pipeline.

        **fit_params : dict of string -> object
            Parameters passed to the ``fit`` method of each step, where
            each parameter name is prefixed such that parameter ``p`` for step
            ``s`` has key ``s__p``.

        Returns
        -------
        Xt : array-like of shape (n_samples, n_transformed_features)
            Transformed samples.

        yt : array-like of shape (n_samples, n_transformed_features)
            Transformed target.
        """
        last_step = self._final_estimator
        Xt, yt, fit_params = self._fit(X, y, **fit_params)
        with _print_elapsed_time('Pipeline',
                                 self._log_message(len(self.steps) - 1)):
            if last_step == "passthrough":
                return Xt
            elif hasattr(last_step, "fit_resample"):
                return last_step.fit_resample(Xt, yt, **fit_params)

    @if_delegate_has_method(delegate="_final_estimator")
    def fit_predict(self, X, y=None, **fit_params):
        """Apply `fit_predict` of last step in pipeline after transforms.

        Applies fit_transforms of a pipeline to the data, followed by the
        fit_predict method of the final estimator in the pipeline. Valid
        only if the final estimator implements fit_predict.

        Parameters
        ----------
        X : iterable
            Training data. Must fulfill input requirements of first step of
            the pipeline.

        y : iterable, default=None
            Training targets. Must fulfill label requirements for all steps
            of the pipeline.

        **fit_params : dict of string -> object
            Parameters passed to the ``fit`` method of each step, where
            each parameter name is prefixed such that parameter ``p`` for step
            ``s`` has key ``s__p``.

        Returns
        -------
        y_pred : ndarray of shape (n_samples,)
            The predicted target.
        """
        Xt, yt, fit_params = self._fit(X, y, **fit_params)
        with _print_elapsed_time('Pipeline',
                                 self._log_message(len(self.steps) - 1)):
            y_pred = self.steps[-1][-1].fit_predict(Xt, yt, **fit_params)
        return y_pred

    @if_delegate_has_method(delegate='_final_estimator')
    def predict(self, X, **predict_params):
        """Apply transforms to the data, and predict with the final estimator

        Parameters
        ----------
        X : iterable
            Data to predict on. Must fulfill input requirements of first step
            of the pipeline.

        **predict_params : dict of string -> object
            Parameters to the ``predict`` called at the end of all
            transformations in the pipeline. Note that while this may be
            used to return uncertainties from some models with return_std
            or return_cov, uncertainties that are generated by the
            transformations in the pipeline are not propagated to the
            final estimator.

            .. versionadded:: 0.20

        Returns
        -------
        y_pred : array-like
        """
        Xt = X
        for _, name, transform in self._iter(with_final=False, filter_resample=False):
            if hasattr(transform, "fit_resample"):
                Xt, to_keep_ind, outliers = transform.transform(Xt)
                if to_keep_ind is not None:
                    self.to_keep_ind = to_keep_ind
                    self.outliers = outliers
            else:
                Xt = transform.transform(Xt)
        return self.steps[-1][-1].predict(Xt, **predict_params)

    @if_delegate_has_method(delegate='_final_estimator')
    def predict_proba(self, X, **predict_proba_params):
        """Transform the data, and apply `predict_proba` with the final estimator.

        Call `transform` of each transformer in the pipeline. The transformed
        data are finally passed to the final estimator that calls
        `predict_proba` method. Only valid if the final estimator implements
        `predict_proba`.

        Parameters
        ----------
        X : iterable
            Data to predict on. Must fulfill input requirements of first step
            of the pipeline.

        **predict_proba_params : dict of string -> object
            Parameters to the `predict_proba` called at the end of all
            transformations in the pipeline.

        Returns
        -------
        y_proba : ndarray of shape (n_samples, n_classes)
            Result of calling `predict_proba` on the final estimator.
        """
        Xt = X
        for _, name, transform in self._iter(with_final=False, filter_resample=False):
            if hasattr(transform, "fit_resample"):
                Xt, to_keep_ind, outliers = transform.transform(Xt)
                if to_keep_ind is not None:
                    self.to_keep_ind = to_keep_ind
                    self.outliers = outliers
            else:
                Xt = transform.transform(Xt)
        return self.steps[-1][-1].predict_proba(Xt, **predict_proba_params)

    @property
    def transform(self):
        """Apply transforms, and transform with the final estimator

        This also works where final estimator is ``None``: all prior
        transformations are applied.

        Parameters
        ----------
        X : iterable
            Data to transform. Must fulfill input requirements of first step
            of the pipeline.

        Returns
        -------
        Xt : array-like of shape  (n_samples, n_transformed_features)
        """
        # _final_estimator is None or has transform, otherwise attribute error
        # XXX: Handling the None case means we can't use if_delegate_has_method
        if self._final_estimator != 'passthrough':
            self._final_estimator.transform
        return self._transform

    def _transform(self, X, y=None):
        Xt = X
        yt = y
        for _, _, transform in self._iter():
            Xt, y = transform.transform(Xt, y)
        return Xt, y


def _transform_one(transformer, X, y, weight, **fit_params):
    res, y = transformer.transform(X, y)
    # if we have a weight for this transformer, multiply output
    if weight is None:
        return res, y
    return res * weight, y


def _fit_resample_one(sampler,
                      X,
                      y,
                      message_clsname='',
                      message=None,
                      **fit_params):
    with _print_elapsed_time(message_clsname, message):
        X_res, y_res = sampler.fit_resample(X, y, **fit_params)

        return X_res, y_res, sampler


def make_pipeline(*steps, **kwargs):
    """Construct a Pipeline from the given estimators.

    This is a shorthand for the Pipeline constructor; it does not require, and
    does not permit, naming the estimators. Instead, their names will be set
    to the lowercase of their types automatically.

    Parameters
    ----------
    *steps : list of estimators
        A list of estimators.

    memory : None, str or object with the joblib.Memory interface, default=None
        Used to cache the fitted transformers of the pipeline. By default,
        no caching is performed. If a string is given, it is the path to
        the caching directory. Enabling caching triggers a clone of
        the transformers before fitting. Therefore, the transformer
        instance given to the pipeline cannot be inspected
        directly. Use the attribute ``named_steps`` or ``steps`` to
        inspect estimators within the pipeline. Caching the
        transformers is advantageous when fitting is time consuming.

    verbose : bool, default=False
        If True, the time elapsed while fitting each step will be printed as it
        is completed.

    Returns
    -------
    p : Pipeline

    See Also
    --------
    imblearn.pipeline.Pipeline : Class for creating a pipeline of
        transforms with a final estimator.

    Examples
    --------
    >>> from sklearn.naive_bayes import GaussianNB
    >>> from sklearn.preprocessing import StandardScaler
    >>> make_pipeline(StandardScaler(), GaussianNB(priors=None))
    ... # doctest: +NORMALIZE_WHITESPACE
    Pipeline(steps=[('standardscaler', StandardScaler()),
                    ('gaussiannb', GaussianNB())])
    """
    memory = kwargs.pop("memory", None)
    verbose = kwargs.pop('verbose', False)
    if kwargs:
        raise TypeError(
            'Unknown keyword arguments: "{}"'.format(list(kwargs.keys())[0])
        )
    return Pipeline(
        pipeline._name_estimators(steps), memory=memory, verbose=verbose
    )
