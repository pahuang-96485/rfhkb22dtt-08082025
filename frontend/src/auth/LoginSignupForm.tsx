// src/auth/LoginSignupForm.tsx
"use client";

import { useState } from "react";
import { Input } from "../components/login_ui/input";
import { Button } from "../components/login_ui/button";
import { Card, CardContent } from "../components/login_ui/card";
import { useAuth } from "./AuthContext";

// Combined login and signup form component
export default function LoginSignupForm() {
  // Access authentication methods from context
  const { login, signup } = useAuth();

  // --- State for user credentials ---
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fname, setFname] = useState("");
  const [lname, setLname] = useState("");
  const [role, setRole] = useState<"patient" | "doctor">("patient");
  const [isSignup, setIsSignup] = useState(false);

  // --- State for additional profile fields ---
  const [mobile, setMobile] = useState("1234567890");
  const [city, setCity] = useState("Testville");
  const [province, setProvince] = useState("ON");
  const [address, setAddress] = useState("123 Demo Street");
  const [clinic, setClinic] = useState("Clinic Street");
  const [country, setCountry] = useState("Canada");
  const [license, setLicense] = useState("MD123456");
  const [specialization, setSpecialization] = useState("Family Medicine");
  const [error, setError] = useState("");

  // --- Handle form submission ---
  const handleSubmit = async () => {
    setError("");
    try {
      if (isSignup) {
        // Build signup payload
        const data = {
          email, // the user’s email input, kept for form state & TS validation
          password,
          fname,
          lname,
          MobileNumber: mobile,      
          City: city,   
          Province: province,
          emailid: email,   // Use emailid to match backend expectations
          // Add role-specific fields
          ...(role === "patient"
            ? { Address: address }
            : {
                Location1: clinic,
                Country: country,
                Medical_LICENSE_Number: license,
                Specialization: specialization,
              }),
        };
        await signup(data, role);
      } else {
        await login(email, password);
      }
    } catch (err: any) {
      setError(err.message || "Submission error");
    }
  };

  return (
    <Card className="max-w-md mx-auto mt-10 p-4 shadow-xl">
      <CardContent>
        {/* Form title toggles between Login and Sign Up */}
        <h2 className="text-xl font-semibold mb-4 text-blue-600">
          {isSignup ? "Sign Up" : "Login"}
        </h2>

        {/* Name inputs shown only during signup */}
        {isSignup && (
          <>
            <div className="mb-2">
              <label htmlFor="fname" className="block text-sm font-medium text-gray-700">
                First Name
              </label>
              <Input
                id="fname"
                placeholder="First Name"
                value={fname}
                onChange={(e) => setFname(e.target.value)}
                className="mt-1 w-full"
              />
            </div>
            <div className="mb-2">
              <label htmlFor="lname" className="block text-sm font-medium text-gray-700">
                Last Name
              </label>
              <Input
                id="lname"
                placeholder="Last Name"
                value={lname}
                onChange={(e) => setLname(e.target.value)}
                className="mt-1 w-full"
              />
            </div>
          </>
        )}

        {/* Common email and password inputs */}
        <div className="mb-2">
          <label htmlFor="email" className="block text-sm font-medium text-gray-700">
            Email
          </label>
          <Input
            id="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full"
          />
        </div>
        <div className="mb-2">
          <label htmlFor="password" className="block text-sm font-medium text-gray-700">
            Password
          </label>
          <Input
            id="password"
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full"
          />
        </div>

        {/* Additional profile fields for signup */}
        {isSignup && (
          <>
            <div className="mb-2">
              <label htmlFor="mobile" className="block text-sm font-medium text-gray-700">
                Phone Number
              </label>
              <Input
                id="mobile"
                value={mobile}
                readOnly
                onChange={(e) => setMobile(e.target.value)}
                className="mt-1 w-full"
              />
            </div>
            <div className="mb-2">
              <label htmlFor="city" className="block text-sm font-medium text-gray-700">
                City
              </label>
              <Input
                id="city"
                value={city}
                readOnly
                onChange={(e) => setCity(e.target.value)}
                className="mt-1 w-full"
              />
            </div>
            <div className="mb-2">
              <label htmlFor="province" className="block text-sm font-medium text-gray-700">
                Province
              </label>
              <Input
                id="province"
                value={province}
                readOnly
                onChange={(e) => setProvince(e.target.value)}
                className="mt-1 w-full"
              />
            </div>
            {/* Show address only for patients */}
            {role === "patient" && (
              <div className="mb-2">
                <label htmlFor="address" className="block text-sm font-medium text-gray-700">
                  Address
                </label>
                <Input
                  id="address"
                  value={address}
                  readOnly
                  onChange={(e) => setAddress(e.target.value)}
                  className="mt-1 w-full"
                />
              </div>
            )}
            {/* Show clinic info only for doctors */}
            {role === "doctor" && (
              <>
                <div className="mb-2">
                  <label htmlFor="clinic" className="block text-sm font-medium text-gray-700">
                    Clinic Location
                  </label>
                  <Input
                    id="clinic"
                    value={clinic}
                    readOnly
                    onChange={(e) => setClinic(e.target.value)}
                    className="mt-1 w-full"
                  />
                </div>
                <div className="mb-2">
                  <label htmlFor="country" className="block text-sm font-medium text-gray-700">
                    Country
                  </label>
                  <Input
                    id="country"
                    value={country}
                    readOnly
                    onChange={(e) => setCountry(e.target.value)}
                    className="mt-1 w-full"
                  />
                </div>
                <div className="mb-2">
                  <label htmlFor="license" className="block text-sm font-medium text-gray-700">
                    Medical License Number
                  </label>
                  <Input
                    id="license"
                    value={license}
                    readOnly
                    onChange={(e) => setLicense(e.target.value)}
                    className="mt-1 w-full"
                  />
                </div>
                <div className="mb-2">
                  <label htmlFor="specialization" className="block text-sm font-medium text-gray-700">
                    Specialization
                  </label>
                  <Input
                    id="specialization"
                    value={specialization}
                    readOnly
                    onChange={(e) => setSpecialization(e.target.value)}
                    className="mt-1 w-full"
                  />
                </div>
              </>
            )}

            {/* Role selection dropdown */}
            <div className="mb-2">
              <label htmlFor="role" className="mr-2 block text-sm font-medium text-gray-700">
                Role
              </label>
              <select
                id="role"
                className="mt-1 block w-full border-gray-300 rounded-md text-gray-900"
                value={role}
                onChange={(e) => setRole(e.target.value as "patient" | "doctor")}
              >  
                <option value="patient">Patient</option>
                <option value="doctor">Doctor</option>
              </select>
            </div>
          </>
        )}

        {/* Submit and toggle mode buttons */}
        <Button onClick={handleSubmit} className="w-full mt-2">
          {isSignup ? "Sign Up" : "Login"}
        </Button>
        <Button
          variant="ghost"
          className="w-full mt-2"
          onClick={() => setIsSignup(!isSignup)}
        >
          {isSignup ? "Switch to Login" : "Switch to Sign Up"}
        </Button>

        {/* Error message display */}
        {error && <p className="text-red-500 mt-2">{error}</p>}
      </CardContent>
    </Card>
  );
}