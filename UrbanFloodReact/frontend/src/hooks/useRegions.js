/**
 * useRegions.js
 * Fetches the district→taluk→hobli tree from the API.
 * Manages cascading selection state.
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { API_URL } from '../config';

export function useRegions() {
    const [regionsTree, setRegionsTree] = useState({});
    const [selDistrict, setSelDistrict] = useState('');
    const [selTaluk, setSelTaluk] = useState('');
    const [selHobli, setSelHobli] = useState('');
    const [fetchError, setFetchError] = useState('');

    useEffect(() => {
        axios.get(`${API_URL}/regions`)
            .then(res => setRegionsTree(res.data))
            .catch(() => setFetchError('Could not reach backend. Is the server running?'));
    }, []);

    const districts = Object.keys(regionsTree).sort();
    const taluks = selDistrict ? Object.keys(regionsTree[selDistrict] || {}).sort() : [];
    const hoblis = selDistrict && selTaluk ? (regionsTree[selDistrict]?.[selTaluk] || []) : [];

    const setDistrict = (d) => { setSelDistrict(d); setSelTaluk(''); setSelHobli(''); };
    const setTaluk = (t) => { setSelTaluk(t); setSelHobli(''); };

    return {
        regionsTree, districts, taluks, hoblis,
        selDistrict, selTaluk, selHobli,
        setDistrict, setTaluk, setHobli: setSelHobli,
        fetchError,
    };
}
