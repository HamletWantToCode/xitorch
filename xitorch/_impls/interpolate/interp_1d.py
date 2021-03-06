import numpy as np
import torch
import warnings
from abc import abstractmethod
from xitorch._impls.interpolate.base_interp import BaseInterp
from xitorch._impls.interpolate.extrap_utils import get_extrap_pos, get_extrap_val

class BaseInterp1D(BaseInterp):
    def __init__(self, x, y=None, extrap=None, **unused):
        self._y_is_given = y is not None
        self._extrap = extrap
        self._xmin = torch.min(x, dim=-1, keepdim=True)[0]
        self._xmax = torch.max(x, dim=-1, keepdim=True)[0]
        self._is_periodic_required = False

    def set_periodic_required(self, val):
        self._is_periodic_required = val

    def is_periodic_required(self):
        return self._is_periodic_required

    def __call__(self, xq, y=None):
        # xq: (nrq)
        # y: (*BY, nr)
        if self._y_is_given and y is not None:
            msg = "y has been supplied when initiating this instance. This value of y will be ignored"
            # stacklevel=3 because this __call__ will be called by a wrapper's __call__
            warnings.warn(msg, stacklevel=3)

        extrap = self._extrap
        if self._y_is_given:
            y = self.y
        elif y is None:
            raise RuntimeError("y must be given")
        elif self.is_periodic_required():
            check_periodic_value(y)

        xqinterp_mask = torch.logical_and(xq >= self._xmin, xq <= self._xmax) # (nrq)
        xqextrap_mask = ~xqinterp_mask
        allinterp = torch.all(xqinterp_mask)

        if allinterp:
            return self._interp(xq, y=y)
        elif extrap == "mirror" or extrap == "periodic" or extrap == "bound":
            # extrapolation by mapping it to the interpolated region
            xq2 = xq.clone()
            xq2[xqextrap_mask] = get_extrap_pos(xq[xqextrap_mask], extrap, self._xmin, self._xmax)
            return self._interp(xq2, y=y)
        else:
            # interpolation
            yqinterp = self._interp(xq[xqinterp_mask], y=y) # (*BY, nrq)
            yqextrap = get_extrap_val(xq[xqextrap_mask], y, extrap)

            yq = torch.empty((*y.shape[:-1], xq.shape[-1]), dtype=y.dtype, device=y.device) # (*BY, nrq)
            yq[...,xqinterp_mask] = yqinterp
            yq[...,xqextrap_mask] = yqextrap
            return yq

    @abstractmethod
    def _interp(self, xq, y):
        pass

class CubicSpline1D(BaseInterp1D):
    """
    Perform 1D cubic spline interpolation for non-uniform ``x`` [1]_ [2]_.

    Keyword arguments
    -----------------
    bc_type: str or None
        Boundary condition:

        * ``"natural"``: 2nd grad at the boundaries are 0
        * ``"clamped"``: 1st grad at the boundaries are 0

        If ``None``, it will choose ``"natural"``

    extrap: int, float, 1-element torch.Tensor, str, or None
        Extrapolation option:

        * ``int``, ``float``, or 1-element ``torch.Tensor``: it will pad the extrapolated
          values with the specified values
        * ``"mirror"``: the extrapolation values are mirrored
        * ``"periodic"``: periodic boundary condition. ``y[...,0] == y[...,-1]`` must
          be fulfilled for this condition.
        * ``"bound"``: fill in the extrapolated values with the left or right bound
          values.
        * ``"nan"``: fill the extrapolated values with nan
        * callable: apply this extrapolation function with the extrapolated
          positions and use the output as the values
        * ``None``: choose the extrapolation based on the ``bc_type``. These are the
          pairs:

          * ``"clamped"``: ``"mirror"``
          * other: ``"nan"``

        Default: ``None``

    References
    ----------
    .. [1] SplineInterpolation on Wikipedia,
           https://en.wikipedia.org/wiki/Spline_interpolation#Algorithm_to_find_the_interpolating_cubic_spline)
    .. [2] Carl de Boor, "A Practical Guide to Splines", Springer-Verlag, 1978.
    """
    def __init__(self, x, y=None, bc_type=None, extrap=None, **unused):
        # x: (nr,)
        # y: (*BY, nr)

        # get the default extrapolation method and boundary condition
        if bc_type is None:
            bc_type = "natural"
        extrap = check_and_get_extrap(extrap, bc_type)
        super(CubicSpline1D, self).__init__(x, y, extrap=extrap)

        self.x = x
        if x.ndim != 1:
            raise RuntimeError("The input x must be a 1D tensor")

        bc_types = ["natural", "clamped"]
        if bc_type not in bc_types:
            raise RuntimeError("Unimplemented %s bc_type. Available options: %s" % (bc_type, bc_types))
        self.bc_type = bc_type
        self.set_periodic_required(extrap == "periodic") # or self.bc_type == "periodic"

        # precompute the inverse of spline matrix
        self.spline_mat_inv = _get_spline_mat_inv(x, bc_type) # (nr, nr)
        self.y_is_given = y is not None
        if self.y_is_given:
            if self.is_periodic_required():
                check_periodic_value(y)
            self.y = y
            self.ks = torch.matmul(self.spline_mat_inv, y.unsqueeze(-1)).squeeze(-1)

    def _interp(self, xq, y):
        # https://en.wikipedia.org/wiki/Spline_interpolation#Algorithm_to_find_the_interpolating_cubic_spline
        # get the k-vector (i.e. the gradient at every points)
        if self.y_is_given:
            ks = self.ks
        else:
            ks = torch.matmul(self.spline_mat_inv, y.unsqueeze(-1)).squeeze(-1) # (*BY, nr)

        x = self.x # (nr)

        # find the index location of xq
        nr = x.shape[-1]
        idxr = torch.searchsorted(x, xq, right=False) # (nrq)
        idxr = torch.clamp(idxr, 1, nr-1)
        idxl = idxr - 1 # (nrq) from (0 to nr-2)

        if torch.numel(xq) > torch.numel(x):
            # get the variables needed
            yl = y[...,:-1] # (*BY, nr-1)
            xl = x[...,:-1] # (nr-1)
            dy = y[...,1:] - yl # (*BY, nr-1)
            dx = x[...,1:] - xl # (nr-1)
            a = ks[...,:-1] * dx - dy # (*BY, nr-1)
            b = -ks[...,1:] * dx + dy # (*BY, nr-1)

            # calculate the coefficients for the t-polynomial
            p0 = yl # (*BY, nr-1)
            p1 = (dy + a) # (*BY, nr-1)
            p2 = (b - 2*a) # (*BY, nr-1)
            p3 = a - b # (*BY, nr-1)

            t = (xq - torch.gather(xl, -1, idxl)) / torch.gather(dx, -1, idxl) # (nrq)
            # yq = p0[:,idxl] + t * (p1[:,idxl] + t * (p2[:,idxl] + t * p3[:,idxl])) # (nbatch, nrq)
            # NOTE: lines below do not work if xq and x have batch dimensions
            yq = p3[...,idxl] * t
            yq += p2[...,idxl]
            yq *= t
            yq += p1[...,idxl]
            yq *= t
            yq += p0[...,idxl]
            return yq

        else:
            xl = torch.gather(x, -1, idxl)
            xr = torch.gather(x, -1, idxr)
            yl = y[...,idxl].contiguous()
            yr = y[...,idxr].contiguous()
            kl = ks[...,idxl].contiguous()
            kr = ks[...,idxr].contiguous()

            dxrl = xr - xl # (nrq,)
            dyrl = yr - yl # (nbatch, nrq)

            # calculate the coefficients of the large matrices
            t = (xq - xl) / dxrl # (nrq,)
            tinv = 1 - t # nrq
            tta = t*tinv*tinv
            ttb = t*tinv*t
            tyl = tinv + tta - ttb
            tyr = t - tta + ttb
            tkl = tta * dxrl
            tkr = -ttb * dxrl

            yq = yl*tyl + yr*tyr + kl*tkl + kr*tkr
            return yq

    def getparamnames(self):
        if self.y_is_given:
            res = ["x", "y", "ks"]
        else:
            res = ["spline_mat_inv", "x"]
        return res

def check_and_get_extrap(extrap, bc_type):
    if extrap is None:
        return {
            "natural": "nan",
            "clamped": "mirror",
        }[bc_type]
    return extrap

def check_periodic_value(y):
    if not torch.allclose(y[...,0], y[...,-1]):
        raise RuntimeError("The value of y must be periodic to have periodic bc_type or extrap")

# @torch.jit.script
def _get_spline_mat_inv(x:torch.Tensor, bc_type:str):
    """
    Returns the inverse of spline matrix where the gradient can be obtained just
    by

    >>> spline_mat_inv = _get_spline_mat_inv(x, transpose=True)
    >>> ks = torch.matmul(y, spline_mat_inv)

    where `y` is a tensor of (nbatch, nr) and `spline_mat_inv` is the output of
    this function with shape (nr, nr)

    Arguments
    ---------
    x: torch.Tensor with shape (*BX, nr)
        The x-position of the data
    bc_type: str
        The boundary condition

    Returns
    -------
    mat: torch.Tensor with shape (*BX, nr, nr)
        The inverse of spline matrix.
    """
    nr = x.shape[-1]
    BX = x.shape[:-1]
    matshape = (*BX, nr, nr)

    device = x.device
    dtype = x.dtype

    # construct the matrix for the left hand side
    dxinv0 = 1./(x[...,1:] - x[...,:-1]) # (*BX,nr-1)
    zero_pad = torch.zeros_like(dxinv0[...,:1])
    dxinv = torch.cat((zero_pad, dxinv0, zero_pad), dim=-1)
    diag = (dxinv[...,:-1] + dxinv[...,1:]) * 2 # (*BX,nr)
    offdiag = dxinv0 # (*BX,nr-1)
    spline_mat = torch.zeros(matshape, dtype=dtype, device=device)
    spdiag = spline_mat.diagonal(dim1=-2, dim2=-1) # (*BX, nr)
    spudiag = spline_mat.diagonal(offset=1, dim1=-2, dim2=-1)
    spldiag = spline_mat.diagonal(offset=-1, dim1=-2, dim2=-1)
    spdiag[...,:] = diag
    spudiag[...,:] = offdiag
    spldiag[...,:] = offdiag

    # construct the matrix on the right hand side
    dxinv2 = (dxinv * dxinv) * 3
    diagr = (dxinv2[...,:-1] - dxinv2[...,1:])
    udiagr = dxinv2[...,1:-1]
    ldiagr = -udiagr
    matr = torch.zeros(matshape, dtype=dtype, device=device)
    matrdiag = matr.diagonal(dim1=-2, dim2=-1)
    matrudiag = matr.diagonal(offset=1, dim1=-2, dim2=-1)
    matrldiag = matr.diagonal(offset=-1, dim1=-2, dim2=-1)
    matrdiag[...,:] = diagr
    matrudiag[...,:] = udiagr
    matrldiag[...,:] = ldiagr

    if bc_type == "clamped":
        spline_mat[...,0,:] = 0.
        spline_mat[...,0,0] = 1.
        spline_mat[...,-1,:] = 0.
        spline_mat[...,-1,-1] = 1.
        matr[...,0,:] = 0.
        matr[...,-1,:] = 0.

    # solve the matrix inverse
    spline_mat_inv, _ = torch.solve(matr, spline_mat)

    # return to the shape of x
    return spline_mat_inv
