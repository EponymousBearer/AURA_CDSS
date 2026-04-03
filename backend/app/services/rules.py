"""
Rule-based dosing engine for antibiotic recommendations.
Applies clinical dosing rules based on patient factors.
"""

from typing import Dict, Any, Optional
import logging

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DosingRuleEngine:
    """
    Rule-based engine for determining antibiotic dosing.
    Applies clinical rules based on patient demographics and clinical status.
    """

    def __init__(self):
        """Initialize dosing rule engine with default dosing data."""
        self._init_dosing_database()

    def _init_dosing_database(self) -> None:
        """
        Initialize default dosing database.
        Based on standard clinical guidelines.
        """
        self.dosing_db = {
            # Cephalosporins
            "Ceftriaxone": {
                "adult_dose": "1-2 g",
                "pediatric_dose": "50-75 mg/kg",
                "frequency": "Every 24 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": False,
                "notes": "First-line therapy for many Gram-negative infections"
            },
            "Cefepime": {
                "adult_dose": "1-2 g",
                "pediatric_dose": "50 mg/kg",
                "frequency": "Every 8-12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Broad-spectrum cephalosporin with antipseudomonal activity"
            },
            "Ceftazidime": {
                "adult_dose": "1-2 g",
                "pediatric_dose": "50 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Excellent antipseudomonal activity"
            },
            "Cefazolin": {
                "adult_dose": "1-2 g",
                "pediatric_dose": "25 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "5-7 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "First-generation cephalosporin for Gram-positive coverage"
            },

            # Penicillins
            "Piperacillin-Tazobactam": {
                "adult_dose": "3.375 g",
                "pediatric_dose": "75 mg/kg (piperacillin component)",
                "frequency": "Every 6 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Broad-spectrum with antipseudomonal and beta-lactamase coverage"
            },
            "Ampicillin": {
                "adult_dose": "1-2 g",
                "pediatric_dose": "25-50 mg/kg",
                "frequency": "Every 4-6 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Narrow spectrum for susceptible organisms"
            },
            "Amoxicillin": {
                "adult_dose": "500 mg",
                "pediatric_dose": "20-40 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "5-10 days",
                "route_iv": False,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Oral agent for mild infections"
            },
            "Amoxicillin-Clavulanate": {
                "adult_dose": "875/125 mg",
                "pediatric_dose": "45 mg/kg (amoxicillin component)",
                "frequency": "Every 12 hours",
                "duration": "5-10 days",
                "route_iv": False,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Beta-lactamase inhibitor combination"
            },

            # Carbapenems
            "Meropenem": {
                "adult_dose": "1 g",
                "pediatric_dose": "20 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Broad-spectrum reserve agent for MDR organisms"
            },
            "Imipenem": {
                "adult_dose": "500 mg",
                "pediatric_dose": "15-25 mg/kg",
                "frequency": "Every 6 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Broad-spectrum with CNS penetration"
            },
            "Ertapenem": {
                "adult_dose": "1 g",
                "pediatric_dose": "15 mg/kg",
                "frequency": "Every 24 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": False,
                "notes": "Once-daily carbapenem, no Pseudomonas coverage"
            },

            # Fluoroquinolones
            "Ciprofloxacin": {
                "adult_dose": "400 mg",
                "pediatric_dose": "Not routinely recommended",
                "frequency": "Every 12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Excellent Gram-negative coverage including Pseudomonas"
            },
            "Levofloxacin": {
                "adult_dose": "750 mg",
                "pediatric_dose": "Not routinely recommended",
                "frequency": "Every 24 hours",
                "duration": "5-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Good respiratory pathogen coverage"
            },
            "Moxifloxacin": {
                "adult_dose": "400 mg",
                "pediatric_dose": "Not routinely recommended",
                "frequency": "Every 24 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Enhanced Gram-positive and anaerobic coverage"
            },

            # Aminoglycosides
            "Gentamicin": {
                "adult_dose": "5-7 mg/kg",
                "pediatric_dose": "2.5 mg/kg",
                "frequency": "Every 24 hours (or traditional dosing)",
                "duration": "5-7 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Synergy agent for Gram-positive infections"
            },
            "Tobramycin": {
                "adult_dose": "5-7 mg/kg",
                "pediatric_dose": "2.5 mg/kg",
                "frequency": "Every 24 hours",
                "duration": "7-10 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Preferred for Pseudomonas"
            },
            "Amikacin": {
                "adult_dose": "15 mg/kg",
                "pediatric_dose": "7.5 mg/kg",
                "frequency": "Every 24 hours",
                "duration": "7-10 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Reserve aminoglycoside for resistant organisms"
            },

            # Glycopeptides
            "Vancomycin": {
                "adult_dose": "15-20 mg/kg",
                "pediatric_dose": "15 mg/kg",
                "frequency": "Every 8-12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,  # PO only for C. diff
                "renal_adjustment": True,
                "notes": "First-line for MRSA, requires therapeutic drug monitoring"
            },

            # Oxazolidinones
            "Linezolid": {
                "adult_dose": "600 mg",
                "pediatric_dose": "10 mg/kg",
                "frequency": "Every 12 hours",
                "duration": "14-28 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Excellent bioavailability, good for VRE"
            },

            # Lipopeptides
            "Daptomycin": {
                "adult_dose": "6-10 mg/kg",
                "pediatric_dose": "Not established",
                "frequency": "Every 24 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": True,
                "notes": "Bactericidal for VRE and MRSA, monitor CPK"
            },

            # Tetracyclines
            "Tigecycline": {
                "adult_dose": "100 mg loading, then 50 mg",
                "pediatric_dose": "Not established",
                "frequency": "Every 12 hours",
                "duration": "5-14 days",
                "route_iv": True,
                "route_po": False,
                "renal_adjustment": False,
                "notes": "Broad coverage including MDR organisms"
            },
            "Doxycycline": {
                "adult_dose": "100 mg",
                "pediatric_dose": "2 mg/kg",
                "frequency": "Every 12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Oral/IV option with good tissue penetration"
            },
            "Minocycline": {
                "adult_dose": "200 mg loading, then 100 mg",
                "pediatric_dose": "4 mg/kg",
                "frequency": "Every 12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Activity against Acinetobacter and resistant organisms"
            },

            # Others
            "Metronidazole": {
                "adult_dose": "500 mg",
                "pediatric_dose": "7.5 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "7-10 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Anaerobic coverage"
            },
            "Clindamycin": {
                "adult_dose": "600 mg",
                "pediatric_dose": "10 mg/kg",
                "frequency": "Every 8 hours",
                "duration": "7-10 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": False,
                "notes": "Good for skin/soft tissue infections"
            },
            "Trimethoprim-Sulfamethoxazole": {
                "adult_dose": "160/800 mg",
                "pediatric_dose": "8/40 mg/kg",
                "frequency": "Every 12 hours",
                "duration": "7-14 days",
                "route_iv": True,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "Good for UTIs and some resistant organisms"
            },
            "Nitrofurantoin": {
                "adult_dose": "100 mg",
                "pediatric_dose": "Not recommended",
                "frequency": "Every 12 hours",
                "duration": "5-7 days",
                "route_iv": False,
                "route_po": True,
                "renal_adjustment": True,
                "notes": "UTI only, avoid in CrCl <30"
            }
        }

    def get_dosing(self,
                   antibiotic: str,
                   age: int,
                   kidney_function: str,
                   severity: str) -> Dict[str, str]:
        """
        Get dosing information for an antibiotic based on patient factors.

        Args:
            antibiotic: Antibiotic name
            age: Patient age in years
            kidney_function: 'normal' or 'low'
            severity: 'low', 'medium', or 'high'

        Returns:
            Dictionary with dose, route, frequency, duration, and notes
        """
        kidney_function = str(kidney_function).strip().lower()
        severity = str(severity).strip().lower()

        # Get base dosing info
        dosing_info = self.dosing_db.get(antibiotic, {})

        if not dosing_info:
            logger.warning(f"No dosing info found for {antibiotic}")
            return {
                "dose": "Consult pharmacy",
                "route": "IV",
                "frequency": "Per protocol",
                "duration": "Per clinical response",
                "notes": "No standard dosing available"
            }

        # Start with adult dosing
        dose = dosing_info.get("adult_dose", "Consult pharmacy")

        # Determine route based on severity and availability
        route = self._determine_route(dosing_info, severity)

        # Apply kidney function adjustments
        if dosing_info.get("renal_adjustment", False):
            dose = self._adjust_for_renal(dose, antibiotic, kidney_function)

        # Get other parameters
        frequency = dosing_info.get("frequency", "Per protocol")
        duration = self._adjust_duration(dosing_info.get("duration", "7 days"), severity)
        notes = dosing_info.get("notes", "")

        # Add severity-specific notes
        if severity in {"high", "critical"}:
            notes += " | High severity: Consider combination therapy and close monitoring"
        if severity == "critical":
            notes += " | Critical severity: Escalate to ICU-level monitoring and source control"

        return {
            "dose": dose,
            "route": route,
            "frequency": frequency,
            "duration": duration,
            "notes": notes
        }

    def _determine_route(self, dosing_info: Dict[str, Any], severity: str) -> str:
        """
        Determine route of administration based on severity and availability.

        Args:
            dosing_info: Dosing information dictionary
            severity: Severity level

        Returns:
            Route string ('IV' or 'PO')
        """
        # High and critical severity require IV
        if severity in {"high", "critical"}:
            return "IV"

        # Lower severity can use oral if available
        if dosing_info.get("route_po", False):
            return "PO"

        return "IV"

    def _adjust_for_renal(self, dose: str, antibiotic: str, kidney_function: str) -> str:
        """
        Adjust dose for reduced kidney function.

        Args:
            dose: Base dose string
            antibiotic: Antibiotic name

        Returns:
            Adjusted dose string
        """
        # Simplified renal adjustments.
        # In production, this would use actual creatinine clearance calculations.
        if kidney_function == "normal":
            return dose

        renal_adjustments = {
            "normal": {
                "Vancomycin": "15 mg/kg (TDM required, extended interval)",
                "Gentamicin": "2.5 mg/kg (extended interval, level monitoring)",
                "Tobramycin": "2.5 mg/kg (extended interval, level monitoring)",
                "Amikacin": "7.5 mg/kg (extended interval, level monitoring)",
                "Ciprofloxacin": "200-400 mg (reduce frequency)",
                "Levofloxacin": "250-500 mg (reduce frequency)",
                "Meropenem": "0.5-1 g (reduce frequency to q12h)",
                "Imipenem": "250-500 mg (reduce frequency)",
                "Piperacillin-Tazobactam": "2.25 g (reduce frequency to q8h)",
                "Ampicillin": "1 g (reduce frequency)",
                "Amoxicillin": "250-500 mg (reduce frequency)",
                "Amoxicillin-Clavulanate": "500/125 mg (reduce frequency)",
                "Cefepime": "1 g (reduce frequency to q24h)",
                "Ceftazidime": "1 g (reduce frequency to q24h)",
                "Cefazolin": "1 g (reduce frequency)",
                "Nitrofurantoin": "AVOID if CrCl <30",
                "Trimethoprim-Sulfamethoxazole": "Reduce frequency to q24h"
            },
            "mild": {
                "Vancomycin": "15 mg/kg (monitor levels, modest interval extension)",
                "Gentamicin": "3 mg/kg (monitor levels, modest interval extension)",
                "Tobramycin": "3 mg/kg (monitor levels, modest interval extension)",
                "Amikacin": "10 mg/kg (monitor levels, modest interval extension)",
                "Ciprofloxacin": "250-400 mg (modest frequency reduction)",
                "Levofloxacin": "250-500 mg (modest frequency reduction)",
                "Meropenem": "0.5-1 g (consider q8-12h)",
                "Imipenem": "250-500 mg (consider reduced frequency)",
                "Piperacillin-Tazobactam": "3.375 g (consider q8h)",
                "Ampicillin": "1-2 g (consider reduced frequency)",
                "Amoxicillin": "250-500 mg (consider reduced frequency)",
                "Amoxicillin-Clavulanate": "500/125 mg (consider reduced frequency)",
                "Cefepime": "1-2 g (consider interval extension)",
                "Ceftazidime": "1-2 g (consider interval extension)",
                "Cefazolin": "1-2 g (consider interval extension)",
                "Nitrofurantoin": "Use with caution; confirm renal function",
                "Trimethoprim-Sulfamethoxazole": "Consider q12-24h adjustment"
            },
            "low": {
                "Vancomycin": "15 mg/kg (TDM required, extended interval)",
                "Gentamicin": "2.5 mg/kg (extended interval, level monitoring)",
                "Tobramycin": "2.5 mg/kg (extended interval, level monitoring)",
                "Amikacin": "7.5 mg/kg (extended interval, level monitoring)",
                "Ciprofloxacin": "200-400 mg (reduce frequency)",
                "Levofloxacin": "250-500 mg (reduce frequency)",
                "Meropenem": "0.5-1 g (reduce frequency to q12h)",
                "Imipenem": "250-500 mg (reduce frequency)",
                "Piperacillin-Tazobactam": "2.25 g (reduce frequency to q8h)",
                "Ampicillin": "1 g (reduce frequency)",
                "Amoxicillin": "250-500 mg (reduce frequency)",
                "Amoxicillin-Clavulanate": "500/125 mg (reduce frequency)",
                "Cefepime": "1 g (reduce frequency to q24h)",
                "Ceftazidime": "1 g (reduce frequency to q24h)",
                "Cefazolin": "1 g (reduce frequency)",
                "Nitrofurantoin": "AVOID if CrCl <30",
                "Trimethoprim-Sulfamethoxazole": "Reduce frequency to q24h"
            },
            "severe": {
                "Vancomycin": "15 mg/kg (TDM required, maximal interval extension)",
                "Gentamicin": "2 mg/kg (maximal interval extension, level monitoring)",
                "Tobramycin": "2 mg/kg (maximal interval extension, level monitoring)",
                "Amikacin": "5-7.5 mg/kg (maximal interval extension, level monitoring)",
                "Ciprofloxacin": "200-400 mg (major frequency reduction)",
                "Levofloxacin": "250 mg (major frequency reduction)",
                "Meropenem": "0.5 g (maximal reduction to q24h/q12-24h)",
                "Imipenem": "250 mg (maximal reduction)",
                "Piperacillin-Tazobactam": "2.25 g (maximal reduction to q12h)",
                "Ampicillin": "1 g (maximal reduction)",
                "Amoxicillin": "250 mg (maximal reduction)",
                "Amoxicillin-Clavulanate": "500/125 mg (maximal reduction)",
                "Cefepime": "1 g (maximal reduction to q24h)",
                "Ceftazidime": "1 g (maximal reduction to q24h)",
                "Cefazolin": "1 g (maximal reduction)",
                "Nitrofurantoin": "AVOID in severe renal impairment",
                "Trimethoprim-Sulfamethoxazole": "Maximal frequency reduction"
            }
        }

        adjustments = renal_adjustments.get(kidney_function, renal_adjustments["low"])
        return adjustments.get(antibiotic, f"{dose} (consider dose reduction)")

    def _adjust_duration(self, base_duration: str, severity: str) -> str:
        """
        Adjust treatment duration based on severity.

        Args:
            base_duration: Base duration string
            severity: Severity level

        Returns:
            Adjusted duration string
        """
        # For simplicity, return base duration with severity note
        # In practice, this could parse and extend/shorten duration
        if severity == "critical":
            if "14-28" in base_duration:
                return "21-28 days (extend for critical infection)"
            if "7-14" in base_duration:
                return "14-21 days (extend for critical infection)"
            if "5-7" in base_duration:
                return "10-14 days (extend for critical infection)"
            return f"{base_duration} (extend for critical infection)"

        if severity == "high":
            if "7-14" in base_duration:
                return "14 days (extend based on clinical response)"
            elif "5-7" in base_duration:
                return "7-10 days"

        return base_duration

    def get_all_antibiotics(self) -> list:
        """
        Get list of all antibiotics in the database.

        Returns:
            List of antibiotic names
        """
        return list(self.dosing_db.keys())

    def get_dosing_details(self, antibiotic: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed dosing information for an antibiotic.

        Args:
            antibiotic: Antibiotic name

        Returns:
            Dosing details dictionary or None if not found
        """
        return self.dosing_db.get(antibiotic)
