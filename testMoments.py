#!/usr/bin/env python3


import math
from typing import Any, Collection, Dict, List, Tuple

from uncertainties import UFloat, ufloat

import ROOT


# see https://root-forum.cern.ch/t/tf1-eval-as-a-function-in-rdataframe/50699/3
def declareInCpp(**kwargs: Any) -> None:
  '''Creates C++ variables (names given by keys) for PyROOT objects (given values) in PyVars:: namespace'''
  for key, value in kwargs.items():
    ROOT.gInterpreter.Declare(  # type: ignore
f'''
namespace PyVars
{{
  auto& {key} = *reinterpret_cast<{type(value).__cpp_name__}*>({ROOT.addressof(value)});
}}
''')


# see e.g. LHCb, PRD 92 (2015) 112009
def generateDataLegPolLC(
  nmbEvents:  int,
  maxDegree:  int,
  parameters: Collection[float],
) -> Tuple[str, str]:
  '''Generates data according to linear combination of Legendre polynomials'''
  assert len(parameters) >= maxDegree + 1, f"Need {maxDegree + 1} parameters; only {len(parameters)} were given: {parameters}"
  # linear combination of legendre polynomials up to given degree
  terms = tuple(f"[{degree}] * ROOT::Math::legendre({degree}, x)" for degree in range(maxDegree + 1))
  legendrePolLC = ROOT.TF1("legendrePolLC", " + ".join(terms), -1, +1)  # type: ignore
  legendrePolLC.SetNpx(1000)  # used in numeric integration performed by GetRandom()
  for index, parameter in enumerate(parameters):
    legendrePolLC.SetParameter(index, parameter)
  legendrePolLC.SetMinimum(0)

  # draw function
  canv = ROOT.TCanvas()  # type: ignore
  legendrePolLC.Draw()
  canv.SaveAs(f"{legendrePolLC.GetName()}.pdf")

  # generate random data that follow linear combination of legendre polynomials
  declareInCpp(legendrePolLC = legendrePolLC)
  treeName = "data"
  fileName = f"{legendrePolLC.GetName()}.root"
  df = ROOT.RDataFrame(nmbEvents)  # type: ignore
  df.Define("cosTheta", "PyVars::legendrePolLC.GetRandom()") \
    .Filter('if (rdfentry_ == 0) { cout << "Running event loop" << endl; } return true;') \
    .Snapshot(treeName, fileName)  # snapshot is needed or else the `cosTheta` column would be regenerated for every triggered loop
                                   # use noop filter to log when event loop is running
  return treeName, fileName


def calculateLegMoments(
  dataFrame: Any,
  maxDegree: int,
) -> Dict[Tuple[int, ...], UFloat]:
  nmbEvents = dataFrame.Count().GetValue()
  moments: Dict[Tuple[int, ...], UFloat] = {}
  for degree in range(maxDegree + 5):
    # unnormalized moments
    dfMoment = dataFrame.Define("legendrePol", f"ROOT::Math::legendre({degree}, cosTheta)")
    momentVal = dfMoment.Sum("legendrePol").GetValue()
    momentErr = math.sqrt(nmbEvents) * dfMoment.StdDev("legendrePol").GetValue()  # iid events: Var[sum_i^N f(x_i)] = sum_i^N Var[f] = N * Var[f]; see https://www.wikiwand.com/en/Monte_Carlo_integration
    # normalize moments with respect to H(0)
    legendrePolIntegral = 1 / (2 * degree + 1)  # = 1/2 * int_-1^+1; factor 1/2 takes into account integral for H(0)
    norm = 1 / (nmbEvents * legendrePolIntegral)
    moment = norm * ufloat(momentVal, momentErr)  # type: ignore
    print(f"H(L = {degree}) = {moment}")
    moments[(degree, )] = moment
  print(moments)
  return moments


# see e.g. Chung, PRD56 (1997) 7299; Suh-Urk's note Techniques of Amplitude Analysis for Two-pseudoscalar Systems; or E852, PRD 60 (1999) 092001
# see also https://en.wikipedia.org/wiki/Spherical_harmonics#Spherical_harmonics_expansion
def generateDataSphHarmLC(
  nmbEvents:  int,
  maxL:       int,
  parameters: Collection[float],  # make sure that resulting linear combination is positive definite
) -> Tuple[str, str]:
  '''Generates data according to linear combination of spherical harmonics'''
  nmbTerms = (maxL + 1) * (2 * maxL + 1) - ((maxL - 1) * (2 * maxL - 1))  # see Eqs. (15) to (17)
  assert len(parameters) >= nmbTerms, f"Need {nmbTerms} parameters; only {len(parameters)} were given: {parameters}"
  # linear combination of spherical harmonics up to given maximum orbital angular momentum
  # using Eq. (12) in Eq. (6): I = sum_L (2 L + 1 ) / (4pi)  H(L 0) (D_00^L)^* + sum_{M = 1}^L H(L M) 2 Re[D_M0^L]
  # and (D_00^L)^* = D_00^L = sqrt(4 pi / (2 L + 1)) (Y_L^0)^* = Y_L^0
  # and Re[D_M0^L] = d_M0^L cos(M phi) = Re[sqrt(4 pi / (2 L + 1)) (Y_L^M)^*] = Re[sqrt(4 pi / (2 L + 1)) Y_L^M]
  # i.e. Eq. (13) becomes: I = sum_L sqrt((2 L + 1 ) / (4pi)) sum_{M = 0}^L tau(M) H(L M) Re[Y_L^M]
  terms = []
  termIndex = 0
  for L in range(2 * maxL + 1):
    termsM = []
    for M in range(min(L, 2) + 1):
      termsM.append(f"[{termIndex}] * {1 if M == 0 else 2} * ROOT::Math::sph_legendre({L}, {M}, std::acos(x)) * std::cos({M} * TMath::DegToRad() * y)")  # ROOT defines this as function of theta (not cos(theta)!); sigh
      termIndex += 1
    terms.append(f"std::sqrt((2 * {L} + 1 ) / (4 * TMath::Pi())) * ({' + '.join(termsM)})")
  print("!!! LC =", " + ".join(terms))
  sphericalHarmLC = ROOT.TF2("sphericalHarmlLC", " + ".join(terms), -1, +1, -180, +180)  # type: ignore
  sphericalHarmLC.SetNpx(100)  # used in numeric integration performed by GetRandom()
  sphericalHarmLC.SetNpy(100)
  for index, parameter in enumerate(parameters):
    sphericalHarmLC.SetParameter(index, parameter)
  sphericalHarmLC.SetMinimum(0)

  # draw function
  canv = ROOT.TCanvas()  # type: ignore
  sphericalHarmLC.Draw("COLZ")
  canv.SaveAs(f"{sphericalHarmLC.GetName()}.pdf")

  # generate random data that follow linear combination of of spherical harmonics
  declareInCpp(sphericalHarmLC = sphericalHarmLC)
  treeName = "data"
  fileName = f"{sphericalHarmLC.GetName()}.root"
  df = ROOT.RDataFrame(nmbEvents)  # type: ignore
  df.Define("point", "double x, y; PyVars::sphericalHarmLC.GetRandom2(x, y); std::vector<double> point = {x, y}; return point;") \
    .Define("cosTheta", "point[0]") \
    .Define("Phi",      "point[1]") \
    .Filter('if (rdfentry_ == 0) { cout << "Running event loop" << endl; } return true;') \
    .Snapshot(treeName, fileName)  # snapshot is needed or else the `point` column would be regenerated for every triggered loop
                                   # use noop filter to log when event loop is running
  return treeName, fileName


def calculateSphHarmMoments(
  dataFrame: Any,
  maxL:      int,
) -> Dict[Tuple[int, ...], UFloat]:
  nmbEvents = dataFrame.Count().GetValue()
  moments: Dict[Tuple[int, ...], UFloat] = {}
  for L in range(2 * maxL + 2):
    for M in range(min(L, 2) + 1):
      # unnormalized moments
      dfMoment = dataFrame.Define("sphericalHarm", f"ROOT::Math::sph_legendre({L}, {M}, std::acos(cosTheta)) * std::cos({M} * TMath::DegToRad() * Phi)")
      momentVal = dfMoment.Sum("sphericalHarm").GetValue()
      momentErr = math.sqrt(nmbEvents) * dfMoment.StdDev("sphericalHarm").GetValue()  # iid events: Var[sum_i^N f(x_i)] = sum_i^N Var[f] = N * Var[f]; see https://www.wikiwand.com/en/Monte_Carlo_integration
      # normalize moments with respect to H(0 0)
      #     Integrate[Re[SphericalHarmonicY[L, M, x, y]] * Sin[x], {y, -Pi, Pi}, {x, 0, Pi}]
      norm = 1 / (nmbEvents * math.sqrt((2 * L + 1) / (4 * math.pi)))
      moment = norm * ufloat(momentVal, momentErr)  # type: ignore
      print(f"H(L = {L}, M = {M}) = {moment}")
      moments[(L, M)] = moment
  print(moments)
  return moments


if __name__ == "__main__":
  ROOT.gROOT.SetBatch(True)  # type: ignore
  ROOT.gRandom.SetSeed(1234567890)  # type: ignore

  # get data
  nmbEvents = 100000
  # maxOrder = 5
  # chose parameters such that resulting linear combinations are positive definite
  # treeName, fileName = generateDataLegPolLC(nmbEvents,  maxDegree = maxOrder, parameters = (1, 1, 0.5, -0.5, -0.25, 0.25))
  # treeName, fileName = generateDataLegPolLC(nmbEvents,  maxDegree = maxOrder, parameters = (0.5, 0.5, 0.25, -0.25, -0.125, 0.125))
  maxOrder = 1
  # treeName, fileName = generateDataSphHarmLC(nmbEvents, maxL = maxOrder, parameters = (1, 0.1, 0.125, -0.075, 0.0625, -0.05))
  treeName, fileName = generateDataSphHarmLC(nmbEvents, maxL = maxOrder, parameters = (2, 0.2, 0.25, -0.15, 0.125, -0.1))
  ROOT.EnableImplicitMT(10)  # type: ignore
  dataFrame = ROOT.RDataFrame(treeName, fileName)  # type: ignore
  # print("!!!", dataFrame.AsNumpy())

  # plot data
  canv = ROOT.TCanvas()  # type: ignore
  if "Phi" in dataFrame.GetColumnNames():
    hist = dataFrame.Histo2D(ROOT.RDF.TH2DModel("data", "", 25, -1, +1, 25, -180, +180), "cosTheta", "Phi")  # type: ignore
    hist.SetMinimum(0)
    hist.Draw("COLZ")
  else:
    hist = dataFrame.Histo1D(ROOT.RDF.TH1DModel("data", "", 100, -1, +1), "cosTheta")  # type: ignore
    hist.SetMinimum(0)
    hist.Draw()
  canv.SaveAs(f"{hist.GetName()}.pdf")

  # calculate moments
  # calculateLegMoments(dataFrame, maxDegree = maxOrder)
  calculateSphHarmMoments(dataFrame, maxL = maxOrder)
