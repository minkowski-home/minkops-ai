import { useState } from 'react';
import './InterestForm.css';

export default function InterestForm() {
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        company: '',
        interest: 'general',
        message: ''
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        console.log("Form submitted:", formData);
        // Add submission logic here
        alert("Thanks for your interest! We'll be in touch.");
    };

    return (
        <div className="interest-form-container">
            <h2 className="form-title">Request Access</h2>
            <p className="form-subtitle">Join the waiting list for our autonomous workforce.</p>
            
            <form onSubmit={handleSubmit} className="glass-form">
                <div className="form-group">
                    <label htmlFor="name">Full Name</label>
                    <input
                        type="text"
                        id="name"
                        name="name"
                        value={formData.name}
                        onChange={handleChange}
                        required
                        placeholder="Sarah Connor"
                    />
                </div>

                <div className="form-group">
                    <label htmlFor="email">Work Email</label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        value={formData.email}
                        onChange={handleChange}
                        required
                        placeholder="sarah@skynet.com"
                    />
                </div>

                <div className="form-group">
                    <label htmlFor="company">Company</label>
                    <input
                        type="text"
                        id="company"
                        name="company"
                        value={formData.company}
                        onChange={handleChange}
                        placeholder="Cyberdyne Systems"
                    />
                </div>

                <div className="form-group">
                    <label htmlFor="interest">Primary Interest</label>
                    <div className="select-wrapper">
                        <select
                            id="interest"
                            name="interest"
                            value={formData.interest}
                            onChange={handleChange}
                        >
                            <option value="general">General Inquiry</option>
                            <option value="sales">Sales & Lead Gen</option>
                            <option value="support">Customer Support</option>
                            <option value="marketing">Marketing & Content</option>
                            <option value="operations">Operations & HR</option>
                            <option value="enterprise">Enterprise Custom Solutions</option>
                        </select>
                    </div>
                </div>

                <div className="form-group">
                    <label htmlFor="message">Message (Optional)</label>
                    <textarea
                        id="message"
                        name="message"
                        value={formData.message}
                        onChange={handleChange}
                        rows={4}
                        placeholder="Tell us about your needs..."
                    />
                </div>

                <button type="submit" className="cta-button form-submit">
                    Join Waitlist
                </button>
            </form>
        </div>
    );
}
